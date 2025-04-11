import google.generativeai as genai
from google.api_core import exceptions as google_api_exceptions
import os
import json
import logging
import inspect # To check function signature for 'db' parameter
from dotenv import load_dotenv
from typing import Dict, Any, List
import asyncio
from sqlalchemy.orm import Session # For type hinting

# Import the function map, tool definition getter, and error helper
# AVAILABLE_TOOLS is renamed to AVAILABLE_FUNCTIONS in tools.py now
from .tools import AVAILABLE_FUNCTIONS, get_tool_definitions, _error_response
# Import DB session factory
from ..persistence import database

# Load environment variables (for API key)
# Ensure .env is in the parent directory relative to this file's location
# Or adjust the path based on where the script is run from.
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
load_dotenv(dotenv_path=dotenv_path)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found in environment variables.")

genai.configure(api_key=GEMINI_API_KEY)

# --- Gemini Model Configuration ---
# Use a model that supports function calling, like Gemini 1.5 Pro
MODEL_NAME = "gemini-1.5-pro-latest" # Or specific version

# Instantiate the generative model WITHOUT tools due to schema generation errors
# TODO: Re-enable tools=[get_tool_definitions()] when library issues are resolved or schema is fixed.
logging.warning("Initializing Gemini Model WITHOUT tools due to schema generation errors.")
model = genai.GenerativeModel(
    MODEL_NAME
    # tools=get_tool_definitions() # Temporarily disabled
)

# --- Interaction Logic ---

async def process_natural_language_request(user_prompt: str) -> Dict[str, Any]:
    """
    Processes a natural language request using Gemini with function calling.

    1. Sends the user prompt and available tools to the Gemini API.
    2. If Gemini requests a function call:
       a. Looks up the requested function in AVAILABLE_TOOLS.
       b. Executes the function with the arguments provided by Gemini.
       c. Sends the function's return value back to Gemini.
    3. Returns Gemini's final response (text or structured data).

    Args:
        user_prompt: The natural language query from the user.

    Returns:
        A dictionary containing the final response from Gemini or an error message.
    """
    logging.info(f"Processing Gemini request: '{user_prompt}'")
    # Use the model configured with tools
    chat = model.start_chat(enable_automatic_function_calling=False) # Manual control for clarity

    try:
        # --- Rate Limit Consideration ---
        # Add delays here if hitting Gemini rate limits frequently
        # await asyncio.sleep(1) # Example simple delay

        # Send the first message to Gemini
        logging.debug(f"Sending prompt to Gemini: '{user_prompt}'")
        response = await chat.send_message_async(user_prompt)
        logging.debug(f"Gemini initial response parts: {response.parts}")

        # Check if Gemini responded with a function call request
        if response.parts and response.parts[0].function_call:
            function_call = response.parts[0].function_call
            tool_name = function_call.name
            tool_args = dict(function_call.args) # Convert FunctionCall args to dict

            logging.info(f"Gemini requested function call: {tool_name} with args: {tool_args}")

            # --- Security Check & Tool Availability ---
            # This check is now less relevant as tools are disabled at model init,
            # but keep for defensive programming if tools are re-enabled later.
            if tool_name not in AVAILABLE_FUNCTIONS:
                logging.error(f"Gemini requested a non-existent tool function: {tool_name}")
                error_response_part = genai.Part.from_function_response(
                    name=tool_name,
                    response={"error": f"Tool '{tool_name}' is not available or not recognized."}
                )
                response = await chat.send_message_async(error_response_part)
                # Return an error to the API caller
                return {"error": f"Unknown or disabled tool requested: {tool_name}"}


            # --- Execute the Function ---
            db_session: Optional[Session] = None
            try:
                tool_function = AVAILABLE_TOOLS[tool_name]
                tool_signature = inspect.signature(tool_function)

                # Check if the tool requires a 'db' argument
                requires_db = 'db' in tool_signature.parameters

                call_args = tool_args.copy() # Use provided args

                if requires_db:
                    # Create a new DB session for this tool call
                    logging.debug(f"Tool '{tool_name}' requires DB session. Creating one.")
                    db_session = next(database.get_db())
                    # Inject the session into the arguments
                    call_args['db'] = db_session
                else:
                     logging.debug(f"Tool '{tool_name}' does not require DB session.")

                # --- Argument Sanitization/Validation Note ---
                # As noted before, deeper sanitization should be within the tool itself.

                # Call the function with potentially injected db session
                function_response_data = tool_function(**call_args)
                logging.info(f"Function '{tool_name}' executed. Result: {function_response_data}")

                # --- Send Function Result Back to Gemini ---
                function_response = genai.Part.from_function_response(
                    name=tool_name,
                    response=function_response_data # Pass the dictionary directly
                )

                # Send the function response back to continue the conversation
                logging.debug(f"Sending function response to Gemini for {tool_name}: {function_response_data}")
                response = await chat.send_message_async(function_response)
                logging.debug(f"Gemini final response parts after function call: {response.parts}")

            except Exception as e:
                # Catch errors during the *lookup or calling* of the tool function itself
                # (Errors *within* the tool function should be handled by the tool and returned in function_response_data)
                logging.exception(f"Critical error executing function call for '{tool_name}': {e}")
                # Send error back to Gemini
                error_response_part = genai.Part.from_function_response(
                    name=tool_name,
                    response={"error": f"Failed to execute function {tool_name} due to an internal error: {str(e)}"}
                )
                # Don't await here? If send fails, we have bigger problems. Maybe just log.
                try:
                    # Ensure response is sent even on execution error
                    await chat.send_message_async(error_response_part)
                except Exception as send_err:
                     logging.error(f"Failed to send function execution error back to Gemini: {send_err}")

                # Return error to API caller
                return {"error": f"Failed to execute tool '{tool_name}': {str(e)}"}
            finally:
                 # --- Ensure DB session is closed if created ---
                 if db_session:
                     logging.debug(f"Closing DB session for tool '{tool_name}'.")
                     db_session.close()

        # --- Extract Final Response ---
        # Assuming the final response is text after potential function call
        final_text = None
        try:
            final_text = response.text
        except ValueError:
             # Handle cases where accessing response.text might fail (e.g., if no text part exists)
             logging.warning("Gemini response did not contain a direct text part.")

        if final_text:
            logging.info(f"Final Gemini text response: {final_text}")
            return {"response": final_text}
        elif response.parts and response.parts[0].function_call:
             # This case indicates Gemini wants to call *another* function immediately.
             # For simplicity, we are not handling multi-turn function calls here.
             logging.warning("Gemini responded with another function call; multi-turn calls not handled in this example.")
             return {"error": "Gemini requested follow-up actions not currently supported. Please refine your request."}
        else:
            # Handle cases where Gemini might not return text (e.g., safety settings, finish reason)
            finish_reason = response.candidates[0].finish_reason if response.candidates else "UNKNOWN"
            logging.warning(f"Gemini finished without a text response. Finish reason: {finish_reason}")
            # Check prompt feedback for blocked prompts etc.
            block_reason = response.prompt_feedback.block_reason if response.prompt_feedback else None
            if block_reason:
                 logging.error(f"Gemini request blocked. Reason: {block_reason}")
                 return {"error": f"Request blocked by Gemini. Reason: {block_reason}"}
            # Check for other finish reasons
            if finish_reason != genai.types.FinishReason.STOP:
                 return {"error": f"Gemini interaction finished unexpectedly. Reason: {finish_reason}"}
            return {"response": "(No text content received from Gemini)"}

    # --- Specific Gemini/Google API Error Handling ---
    except google_api_exceptions.ResourceExhausted as e:
        logging.error(f"Gemini API Rate Limit Error: {e}")
        return {"error": "API rate limit exceeded. Please try again later."}
    except google_api_exceptions.InvalidArgument as e:
         logging.error(f"Gemini API Invalid Argument Error: {e}")
         return {"error": f"Invalid request sent to Gemini: {e}"}
    except google_api_exceptions.GoogleAPIError as e:
         logging.error(f"Gemini API Error: {e}")
         return {"error": f"An error occurred while communicating with the AI service: {e}"}
    except Exception as e:
        logging.exception(f"An unexpected error occurred during Gemini interaction: {e}")
        return {"error": f"An unexpected internal error occurred: {str(e)}"}

# --- Example Usage (for testing this module directly) ---
async def main_test():
    # Example prompts - include potentially problematic ones
    prompts = [
        "List all my trading agents.",
        "Create a new grid trading agent named 'BTC Fun Grid' for BTCUSDT between 70k and 60k with 15 levels and $30 per order.", # Invalid range
        "Create an agent with no name", # Invalid name (should be caught by tool)
        "What's the status of agent 'agent-grid-my-grid-bot-123'?",
        "Start agent 'nonexistent-agent-id'", # Agent not found
        "Stop the ETH Arb agent (ID: agent-arbitrage-eth-arb-456).",
        "Show me the detailed performance for 'agent-grid-my-grid-bot-123' over the last 7 days.",
        "Delete the SOL grid bot (agent-grid-sol-grid-789).",
        "Tell me a joke about trading bots." # Example non-tool prompt
        "List all my trading agents.",
        "Create a new grid trading agent named 'BTC Fun Grid' for BTCUSDT between 60k and 70k with 15 levels and $30 per order.",
        "What's the status of agent 'agent-grid-my-grid-bot-123'?",
        "Stop the ETH Arb agent (ID: agent-arbitrage-eth-arb-456).",
        "Show me the detailed performance for 'agent-grid-my-grid-bot-123' over the last 7 days.",
        "Delete the SOL grid bot (agent-grid-sol-grid-789).",
        "Tell me a joke about trading bots." # Example non-tool prompt
    ]

    for prompt in prompts:
        result = await process_natural_language_request(prompt)
        print(f"Result for '{prompt}':\n{json.dumps(result, indent=2)}\n")
        print("-" * 30)

if __name__ == "__main__":
    # Setup logging for testing
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
    import asyncio
    # On Windows, default asyncio event loop policy might cause issues
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main_test())

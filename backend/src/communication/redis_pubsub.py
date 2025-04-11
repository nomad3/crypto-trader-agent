import redis
import json
import logging
import threading
import time
from typing import Callable, Optional, Dict, Any
from decouple import config

log = logging.getLogger(__name__)

# Configuration (add these to .env if not using defaults)
REDIS_HOST = config("REDIS_HOST", default="redis") # Docker service name
REDIS_PORT = config("REDIS_PORT", default=6379, cast=int)
REDIS_DB = config("REDIS_DB", default=0, cast=int)

# Channel names (constants)
AGENT_EVENTS_CHANNEL = "agent_events" # e.g., trade executed, parameter update suggestion
GROUP_UPDATES_CHANNEL = "group_updates" # e.g., aggregated performance, group signals
LEARNING_MODULE_CHANNEL = "learning_module" # For communication with a central learning module

class CommunicationBus:
    """Handles publishing and subscribing to messages using Redis Pub/Sub."""

    def __init__(self):
        self._redis_client: Optional[redis.Redis] = None
        self._pubsub: Optional[redis.client.PubSub] = None
        self._listener_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._connect()

    def _connect(self):
        """Establishes connection to Redis."""
        try:
            self._redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
            self._redis_client.ping()
            self._pubsub = self._redis_client.pubsub(ignore_subscribe_messages=True)
            log.info(f"CommunicationBus connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
        except redis.exceptions.ConnectionError as e:
            log.error(f"Failed to connect to Redis at {REDIS_HOST}:{REDIS_PORT}: {e}")
            self._redis_client = None
            self._pubsub = None
        except Exception as e:
             log.exception(f"Error initializing CommunicationBus: {e}")
             self._redis_client = None
             self._pubsub = None

    def is_ready(self) -> bool:
        """Checks if the connection to Redis is active."""
        return self._redis_client is not None and self._pubsub is not None

    def publish(self, channel: str, message_data: Dict[str, Any]):
        """Publishes a message (as JSON) to a specific Redis channel."""
        if not self.is_ready():
            log.error("Cannot publish message, Redis client not ready.")
            return False
        try:
            message_json = json.dumps(message_data)
            self._redis_client.publish(channel, message_json)
            log.debug(f"Published to channel '{channel}': {message_json}")
            return True
        except redis.exceptions.ConnectionError as e:
            log.error(f"Redis connection error during publish to '{channel}': {e}")
            self._connect() # Attempt to reconnect
            return False
        except Exception as e:
            log.exception(f"Error publishing message to channel '{channel}': {e}")
            return False

    def subscribe(self, channel: str, handler: Callable[[Dict[str, Any]], None]):
        """Subscribes to a channel and registers a handler function."""
        if not self.is_ready():
            log.error(f"Cannot subscribe to channel '{channel}', Redis client not ready.")
            return

        try:
            self._pubsub.subscribe(**{channel: lambda msg: self._message_handler(handler, msg)})
            log.info(f"Subscribed to channel '{channel}'")
            # Start the listener thread if it's not already running
            if self._listener_thread is None or not self._listener_thread.is_alive():
                self._start_listener()
        except redis.exceptions.ConnectionError as e:
             log.error(f"Redis connection error during subscribe to '{channel}': {e}")
             self._connect() # Attempt to reconnect
        except Exception as e:
            log.exception(f"Error subscribing to channel '{channel}': {e}")

    def _message_handler(self, handler: Callable[[Dict[str, Any]], None], message: Dict):
        """Internal handler that decodes JSON and calls the user-provided handler."""
        try:
            data = json.loads(message['data'])
            log.debug(f"Received message on channel '{message['channel']}': {data}")
            handler(data)
        except json.JSONDecodeError:
            log.warning(f"Received non-JSON message on channel '{message['channel']}': {message['data']}")
        except Exception as e:
            log.exception(f"Error processing message from channel '{message['channel']}': {e}")

    def _listener_loop(self):
        """Listens for messages in a loop."""
        log.info("CommunicationBus listener thread started.")
        while not self._stop_event.is_set():
            try:
                if not self.is_ready():
                     log.warning("Redis connection lost in listener thread. Attempting reconnect...")
                     time.sleep(5)
                     self._connect()
                     # Resubscribe to channels if connection is re-established
                     if self.is_ready() and self._pubsub:
                          # This requires storing subscriptions or having components resubscribe
                          log.warning("Need to re-implement channel resubscription logic after reconnect.")
                          # self._pubsub.subscribe(...) # Example - needs stored handlers
                     continue

                # Check for messages with a timeout to allow checking the stop event
                message = self._pubsub.get_message(timeout=1.0)
                # Note: get_message() processes one message at a time if using a handler dict
                # If not using handlers in subscribe, you'd process message here.
                if message is None:
                    continue # Timeout, loop again

            except redis.exceptions.ConnectionError as e:
                 log.error(f"Redis connection error in listener loop: {e}")
                 # Connection lost, attempt reconnect in the next iteration
                 self._redis_client = None
                 self._pubsub = None
                 time.sleep(5) # Wait before retrying connection
            except Exception as e:
                log.exception(f"Error in CommunicationBus listener loop: {e}")
                time.sleep(5) # Avoid tight loop on unexpected errors

        log.info("CommunicationBus listener thread stopped.")
        if self._pubsub:
             self._pubsub.close()
        if self._redis_client:
             self._redis_client.close()

    def _start_listener(self):
        """Starts the listener thread."""
        if self._listener_thread is None or not self._listener_thread.is_alive():
            self._stop_event.clear()
            self._listener_thread = threading.Thread(target=self._listener_loop, daemon=True)
            self._listener_thread.start()
            log.info("CommunicationBus listener thread starting.")

    def stop_listener(self):
        """Stops the listener thread gracefully."""
        if self._listener_thread and self._listener_thread.is_alive():
            log.info("Stopping CommunicationBus listener thread...")
            self._stop_event.set()
            self._listener_thread.join(timeout=5) # Wait for thread to finish
            if self._listener_thread.is_alive():
                 log.warning("CommunicationBus listener thread did not stop gracefully.")
            self._listener_thread = None
        else:
             log.info("CommunicationBus listener thread already stopped.")

# --- Example Usage (Conceptual) ---
# bus = CommunicationBus()
#
# def handle_agent_event(data):
#     print(f"Handler received agent event: {data}")
#
# if bus.is_ready():
#     bus.subscribe(AGENT_EVENTS_CHANNEL, handle_agent_event)
#     # Keep main thread alive or manage bus lifecycle elsewhere
#     # bus.publish(AGENT_EVENTS_CHANNEL, {"agent_id": 123, "event": "trade", "symbol": "BTCUSDT"})
#     # time.sleep(10)
#     # bus.stop_listener()

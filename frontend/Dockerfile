# Stage 1: Build the React application
FROM node:18-alpine as build

WORKDIR /app

# Copy package.json and package-lock.json (if available)
COPY package.json ./
# COPY package-lock.json ./ # Uncomment if you have a lock file

# Install dependencies
# Use --legacy-peer-deps if you encounter peer dependency issues
RUN npm install

# Copy the rest of the frontend application code
COPY . .

# Build the application (replace with your actual build command if different)
# Ensure your build script outputs to the 'build' directory
RUN npm run build

# Stage 2: Serve the static files using Nginx
FROM nginx:1.25-alpine

# Copy the build output from the build stage
COPY --from=build /app/build /usr/share/nginx/html

# Copy a custom Nginx configuration (optional, but recommended for SPAs)
# COPY nginx.conf /etc/nginx/conf.d/default.conf # See example below

# Expose port 80 for Nginx
EXPOSE 80

# Start Nginx
CMD ["nginx", "-g", "daemon off;"]

# --- Example nginx.conf (Save as frontend/nginx.conf if needed) ---
# server {
#     listen 80;
#     server_name localhost; # Adjust if needed

#     root /usr/share/nginx/html;
#     index index.html index.htm;

#     location / {
#         try_files $uri $uri/ /index.html; # Handles client-side routing
#     }

#     # Optional: Proxy API requests to the backend container
#     # location /api {
#     #     proxy_pass http://backend:8000; # Assumes backend service is named 'backend' in docker-compose
#     #     proxy_set_header Host $host;
#     #     proxy_set_header X-Real-IP $remote_addr;
#     #     proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
#     #     proxy_set_header X-Forwarded-Proto $scheme;
#     # }
# }

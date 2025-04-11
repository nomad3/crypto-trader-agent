import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000, // Match the port exposed in docker-compose.yml for frontend
    host: '0.0.0.0', // Allow access from outside the container
    // Optional: Proxy API requests to the backend container during development
    // proxy: {
    //   '/api': { // Adjust if your API routes have a different prefix
    //     target: 'http://localhost:8000', // Target the backend running locally or via Docker port mapping
    //     changeOrigin: true,
    //     // rewrite: (path) => path.replace(/^\/api/, ''), // Remove /api prefix if backend doesn't expect it
    //   },
    // },
  },
  build: {
    outDir: 'build', // Output directory matching Dockerfile COPY command
  },
})

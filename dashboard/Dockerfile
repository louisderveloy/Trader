FROM node:20-alpine

WORKDIR /app

# Expose Vite dev server port
EXPOSE 5173

# Install dependencies and start Vite dev server
# Dependencies are installed at container start to work with volume mounts
CMD ["sh", "-c", "npm install && npm run dev -- --host 0.0.0.0"]

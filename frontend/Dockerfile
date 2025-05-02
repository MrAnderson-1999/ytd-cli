# Stage 1: Build the Vite React app
FROM node:18-alpine AS builder
WORKDIR /app
# Install dependencies with lockfile for reproducible builds
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
# Copy all source, then build
COPY frontend/ .
RUN npm run build

# Stage 2: Serve with Nginx
FROM nginx:stable-alpine
# Remove default site and use our config
RUN rm -rf /etc/nginx/conf.d
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
# Copy built assets
COPY --from=builder /app/dist /usr/share/nginx/html 
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]

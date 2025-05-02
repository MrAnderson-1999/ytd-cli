# Stage 1: Build the Vite React app
FROM node:18-alpine AS builder
WORKDIR /app
# Install dependencies with lockfile for reproducible builds
COPY package.json package-lock.json ./
RUN npm ci                                       # reproduce exact dependency tree :contentReference[oaicite:0]{index=0}
# Copy all source, then build
COPY . .
RUN npm run build                                # outputs static files to /app/dist 

# Stage 2: Serve with Nginx
FROM nginx:stable-alpine
# Remove default site and use our config
RUN rm -rf /etc/nginx/conf.d
COPY nginx.conf /etc/nginx/conf.d/default.conf   # custom routing & proxy rules :contentReference[oaicite:2]{index=2}
# Copy built assets
COPY --from=builder /app/dist /usr/share/nginx/html  # serve production build :contentReference[oaicite:3]{index=3}
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]

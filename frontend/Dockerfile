FROM nginx:stable-alpine

# Copy static app
COPY frontend/index.html /usr/share/nginx/html/index.html

# Copy our custom Nginx config
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]

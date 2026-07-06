# Frontend image — build the Vite bundle, serve it with nginx.
# nginx also reverse-proxies /api and /ws to the backend, so the browser talks
# same-origin (VITE_API_BASE stays empty) exactly like the Vite dev proxy does.

# ---- build stage ----
FROM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# No VITE_API_BASE -> same-origin; nginx handles /api + /ws below.
RUN npm run build

# ---- serve stage ----
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]

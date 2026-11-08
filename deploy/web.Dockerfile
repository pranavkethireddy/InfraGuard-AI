# InfraGuard web: builds the React app and serves it with Caddy, which also proxies /api to the backend,
# so the browser (laptop, iPad, judges) talks to one address and needs no CORS.
FROM node:22-slim AS build
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
ENV VITE_DATA_MODE=live VITE_API_BASE_URL=/api/v1
RUN npx vite build

FROM caddy:2-alpine
COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /src/dist /srv

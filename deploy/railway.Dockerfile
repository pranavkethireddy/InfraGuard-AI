# One container for Railway (or any host that runs a single image): the backend serves the built
# frontend and the API on the same origin, so the app calls /api/v1 with no CORS.
FROM node:22-slim AS web
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
ENV VITE_DATA_MODE=live VITE_API_BASE_URL=/api/v1
RUN npx vite build

FROM python:3.14-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 STATIC_DIR=/app/static LIVE_AUTOSTART=true SIMULATION_ENABLED=true
COPY backend/requirements.txt backend/requirements.txt
COPY ml/requirements.txt ml/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt -r ml/requirements.txt
COPY backend backend
COPY simulator simulator
COPY ml ml
COPY configs configs
COPY data data
COPY contracts contracts
COPY --from=web /src/dist /app/static
EXPOSE 8000
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

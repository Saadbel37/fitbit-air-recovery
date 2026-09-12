# --- stage 1: build the frontend ---
FROM node:20-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- stage 2: python runtime serving API + built SPA ---
FROM python:3.12-slim AS runtime
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOST=0.0.0.0 \
    PORT=8080 \
    SIGNALS_DATA_DIR=/data \
    FITBIT_TOKEN_FILE=/data/.fitbit_tokens.json

COPY requirements.txt ./
RUN pip install -r requirements.txt

# application code
COPY backend/ ./backend/
COPY fitbit_mcp/ ./fitbit_mcp/
# built frontend at the path the API expects (project/frontend/dist)
COPY --from=frontend /build/dist ./frontend/dist

# persistent data (SQLite + OAuth tokens) lives on a mounted volume
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8080
CMD ["python", "-m", "backend.api.main"]

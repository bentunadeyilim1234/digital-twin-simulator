# FastAPI simulation engine. Build from the repository root:
#   docker build -f backend/Dockerfile -t ssrdt-api .
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    TWIN_CONFIG_DIR=/app/config TWIN_DB_PATH=/data/twin.sqlite3 PORT=8000
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY config ./config
COPY backend ./backend
RUN useradd --create-home app && mkdir -p /data && chown app /data
USER app
WORKDIR /app/backend
EXPOSE 8000
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT} --workers 1"]

FROM node:20-alpine AS frontend-builder

WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

COPY backend/requirements_backend.txt ./backend/requirements_backend.txt
RUN pip install --no-cache-dir -r backend/requirements_backend.txt

COPY . .
COPY --from=frontend-builder /frontend/dist ./frontend/dist

EXPOSE 8000

CMD ["sh", "-c", "exec python -m uvicorn backend.main_api:app --host 0.0.0.0 --port ${PORT:-8000}"]

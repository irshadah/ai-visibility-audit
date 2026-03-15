# Multi-stage: build frontend, then serve with Python (no Playwright in image)
ARG NODE_VERSION=20-alpine
ARG PYTHON_VERSION=3.12-slim

# ---- Frontend ----
FROM node:${NODE_VERSION} AS frontend
WORKDIR /app
COPY web/frontend/package.json web/frontend/package-lock.json ./
RUN npm ci
COPY web/frontend/ ./
RUN npm run build

# ---- Backend + runtime ----
FROM python:${PYTHON_VERSION}
WORKDIR /app

# Python deps (no Playwright to keep image small)
COPY web/backend/requirements-railway.txt ./web/backend/
RUN pip install --no-cache-dir -r web/backend/requirements-railway.txt

# App and built frontend
COPY python/ ./python/
COPY web/backend/ ./web/backend/
COPY scripts/ ./scripts/
COPY --from=frontend /app/dist ./web/frontend/dist

# App runs from backend dir so ROOT = /app
WORKDIR /app/web/backend
ENV PYTHONPATH=/app/python/src
ENV FLASK_ENV=production
EXPOSE 5001

CMD ["sh", "-c", "exec gunicorn -w 2 -b 0.0.0.0:${PORT:-5001} app:app"]

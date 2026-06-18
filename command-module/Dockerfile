# Stage 1: Build Vue frontend
FROM node:22-slim AS frontend-builder
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# Stage 2: Python application
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/
COPY --from=frontend-builder /frontend/dist ./src/frontend/dist

RUN groupadd --gid 1000 peekaboo && useradd -u 1000 -g 1000 -m -s /bin/bash peekaboo
USER peekaboo

WORKDIR /app/src
EXPOSE 8081
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8081"]

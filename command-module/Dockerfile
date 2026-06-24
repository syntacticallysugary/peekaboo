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

# Optional HTTPS support: if TLS_CERTFILE and TLS_KEYFILE env vars are set, uvicorn will enable SSL.
# See docs/HTTPS_SETUP.md for certificate generation and configuration.
CMD [ \
  "sh", "-c", \
  "uvicorn main:app --host 0.0.0.0 --port 8081 ${TLS_CERTFILE:+--ssl-certfile=$TLS_CERTFILE} ${TLS_KEYFILE:+--ssl-keyfile=$TLS_KEYFILE}" \
  ]

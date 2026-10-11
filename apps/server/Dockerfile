# Build from the repository root: docker build -f apps/server/Dockerfile .
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

COPY packages/bimdelta-core packages/bimdelta-core
COPY apps/server apps/server
RUN pip install --no-cache-dir ./packages/bimdelta-core ./apps/server

EXPOSE 8001

# Hosts such as Render assign the port through $PORT.
CMD ["sh", "-c", "exec uvicorn bimdelta_server.main:app --host 0.0.0.0 --port ${PORT:-8001}"]

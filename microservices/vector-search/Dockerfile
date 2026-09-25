# ALGO-16 Vector Search Service Dockerfile

FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Real, confirmed bug fixed 2026-09-25 (found before building, by
# checking for the same COPY-path mistake that broke
# analysearch-intent's Dockerfile the same round): docker-compose.yml's
# build.context for this service is ".." (the repo root, same as every
# other service), so `COPY app/ ./app/` looked for a repo-root app/
# directory - which does not exist (the real code is at
# microservices/vector-search/app/). This wasn't a silent runtime
# crash like analysearch-intent's version - it fails the `docker build`
# itself, since COPY validates its source path exists.
COPY microservices/vector-search/app/ ./app/

# Environment variables
ENV BACKEND=faiss
ENV DIMENSION=768
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8016

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8016/vector/health')"

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8016"]

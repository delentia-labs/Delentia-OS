# intent-loop Dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY microservices/intent-loop/ /app/microservices/intent-loop/
COPY core/ /app/core/
COPY signedai/ /app/signedai/

# Real, confirmed need (2026-09-24): same bug class as gateway-api's
# Dockerfile (see its own comment here) - "microservices.intent-loop.main"
# is not a valid Python import path because "intent-loop" contains a
# hyphen. main.py's own top-of-file sys.path.insert(0, current_dir) call
# confirms it was designed to be imported as a top-level "main" module
# from within its own directory, not as a "microservices.intent-loop"
# package.
ENV PYTHONPATH=/app:/app/microservices/intent-loop
ENV PYTHONUNBUFFERED=1

EXPOSE 8001

HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]

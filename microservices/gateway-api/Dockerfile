# gateway-api Dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY microservices/gateway-api/ /app/microservices/gateway-api/
COPY core/ /app/core/
COPY signedai/ /app/signedai/

# Real, confirmed need (2026-09-24): "microservices.gateway-api.gateway_main"
# is not a valid Python import path - "gateway-api" contains a hyphen,
# which Python's import grammar rejects (this is a hard syntax rule, not
# a runtime maybe - `import a.b-c.d` is a SyntaxError). uvicorn would fail
# to import the app and the container would never actually serve traffic.
# gateway_main.py's own top-of-file sys.path.insert(0, current_dir) call
# already shows it was designed to be imported as a top-level module from
# within its own directory, not as a "microservices.gateway-api" package -
# PYTHONPATH includes that directory directly so "gateway_main" resolves
# without a hyphenated segment anywhere in the import path.
ENV PYTHONPATH=/app:/app/microservices/gateway-api
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "gateway_main:app", "--host", "0.0.0.0", "--port", "8000"]

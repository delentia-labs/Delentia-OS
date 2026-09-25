FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Real, confirmed bug fixed 2026-09-25 (found via an actual docker build +
# run, not guessed): docker-compose.yml's own build.context for this
# service is ".." (the repo root, same as every other service here) - a
# bare `COPY . .` under that context copies the WHOLE repo tree flatly
# into /app, so the CMD's "app.main:app" import looked for
# /app/app/main.py, which never existed (the real file is at
# microservices/analysearch-intent/app/main.py) - every container start
# crashed with ModuleNotFoundError: No module named 'app'. This service's
# own app/ package has no imports from repo-root core/ or
# rct_control_plane (confirmed via grep), so only its own directory needs
# copying - PYTHONPATH points uvicorn's "app.main" import at it, same
# technique gateway-api's Dockerfile already uses for its own top-level
# import.
COPY microservices/analysearch-intent/ /app/microservices/analysearch-intent/

ENV PYTHONPATH=/app/microservices/analysearch-intent
ENV PYTHONUNBUFFERED=1

EXPOSE 8020

HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8020/analysearch/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8020"]

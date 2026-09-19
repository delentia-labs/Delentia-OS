# Real, minimal container for the Delentia-OS Python kernel API.
# Round 32 (Phase 40): deployment PREP only - this is not deployed to any
# real host by this round. Runs the exact same `uvicorn` invocation already
# proven working locally in Round 31's manual end-to-end HTTP bridge
# verification (real curl calls to /v1/kernel/fdia/evaluate succeeded).
#
# NOTE: Docker's CLI is installed on the dev machine this was written on,
# but the daemon was not running when this file was authored, so a real
# `docker build` could not be verified this round - honestly disclosed,
# not silently assumed to work. Verify with `docker build -t delentia-os .`
# once the daemon is available.

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "rct_control_plane.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

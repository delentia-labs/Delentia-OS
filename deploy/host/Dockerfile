# syntax=docker/dockerfile:1
# Delentia host image (Round 55): the whole runtime, started the way a host starts it (`delentia serve`), as a non-root user.
#
# Status: built and run on Docker Desktop (Round 55); the first build takes several minutes (torch, the 41 algorithms' dependencies). Run
# `delentia host-check` inside the container before opening any port.
#
# Differences from ../../Dockerfile (the kernel-API image):
#   * runs `delentia serve`, which turns on the daemon, the 41-algorithm pipeline, warm recall, the starter skills and the rate limit
#     (the old image ran bare uvicorn: none of those were on);
#   * runs as an unprivileged user (uid 10001), data in /data (a volume), nothing secret in the image (see ../../.dockerignore);
#   * a healthcheck.
FROM python:3.12-slim

RUN useradd --no-create-home --uid 10001 --shell /usr/sbin/nologin delentia \
    && mkdir -p /data/home /app /notary && chown -R delentia:delentia /data /app && chown 10002:10002 /notary

WORKDIR /app
COPY --chown=delentia:delentia . .

# Same dependency steps as the repository Dockerfile, for the same reasons (CPU-only torch wheel; the kernel imports every algorithm's
# dependencies at start-up so the `full` extras are required; headless OpenCV installed last so no GUI libraries are needed).
# The pip cache is a BuildKit cache mount, not an image layer: the first build downloads several GB; later builds (any source change
# invalidates this layer through the COPY above) reuse the downloaded wheels instead of fetching them again.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install -r requirements.txt \
    && pip install -e ".[full]" \
    && pip install --force-reinstall --no-deps opencv-python-headless

USER delentia
ENV DELENTIA_HOME=/data \
    HOME=/data/home \
    PYTHONUNBUFFERED=1

VOLUME ["/data"]
EXPOSE 8000

# /health is public by design (no data). The first start loads every algorithm: allow it time (~20 s measured on a laptop-class CPU).
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

# `delentia serve --host 0.0.0.0` refuses to start without DELENTIA_API_TOKEN or a per-person tokens file: that is deliberate.
CMD ["delentia", "serve", "--host", "0.0.0.0", "--port", "8000"]

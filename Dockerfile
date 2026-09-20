# Real container for the Delentia-OS Python kernel API. Runs the exact
# same `uvicorn` invocation already proven working locally (real curl
# calls to /v1/kernel/fdia/evaluate succeeded in Rounds 31-35).
#
# Round 35: a real `docker build` (Docker Desktop's engine finally
# running) found the `requirements.txt`-only install from Round 32
# insufficient - algorithm_kernel_41.py is a monolithic module that
# imports ALL 41 algorithms' dependencies at load time (constructing
# ALGORITHM_KERNEL, needed even for the single-algorithm FDIA bridge
# endpoint), so it genuinely needs pyproject.toml's optional extras
# too, not just the base requirements. Installing the full project with
# extras here is the honest reflection of that real dependency
# footprint, not a workaround.

FROM python:3.12-slim

WORKDIR /app

COPY . .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -e ".[web-intelligence,vector,ml,integrations]"

EXPOSE 8000

CMD ["uvicorn", "rct_control_plane.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

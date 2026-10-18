# DAAES arm H0 (Hermes Agent as the reference system), Round 86.
#
# Hermes runs INSIDE this container and nowhere else: the container is the sandbox. It receives only the case workspace (mounted at /work) and one model endpoint. No secret of ours is baked in or passed.
# The vendor's installer is not piped into a shell: it is read first, copied into the build context as install.sh, and refused here unless its SHA-256 is the one that was read.
#
#   docker build -t daaes-hermes:r86 --build-arg INSTALL_SHA256=<sha of the script you read> research/daaes/hermes_arm   (with install.sh copied next to this file)
FROM ubuntu:24.04

ARG INSTALL_SHA256
RUN apt-get update && apt-get install -y --no-install-recommends curl git ca-certificates xz-utils procps ripgrep python3 python3-pytest libatomic1 && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --uid 1500 --shell /bin/bash hermes
COPY install.sh /tmp/install.sh
RUN test -n "$INSTALL_SHA256" && echo "${INSTALL_SHA256}  /tmp/install.sh" | sha256sum -c -
USER hermes
ENV HOME=/home/hermes HERMES_HOME=/home/hermes/.hermes
RUN bash /tmp/install.sh --non-interactive --skip-browser --channel stable
# The installer keeps Hermes' dependencies in its own managed store. The benchmark drives Hermes through its Python API (as the Windows adapter does), so give it an ordinary virtual environment made
# with the interpreter the installer fetched, and the pinned source installed editable into it (exact-pinned dependencies from Hermes' own pyproject).
RUN PY=$(ls -d /home/hermes/.hermes/tools/python-3.14*/bin/python3 | head -1) && $PY -m venv /home/hermes/venv && /home/hermes/venv/bin/pip install --quiet -e /home/hermes/.hermes/hermes-agent
ENV PATH=/home/hermes/.local/bin:$PATH
WORKDIR /work

# Real container for the Delentia-OS Python kernel API. Runs the exact
# same `uvicorn` invocation already proven working locally (real curl
# calls to /v1/kernel/fdia/evaluate succeeded in Rounds 31-35).
#
# Round 35: algorithm_kernel_41.py is a monolithic module that imports
# ALL 41 algorithms' dependencies at load time (constructing
# ALGORITHM_KERNEL, needed even for the single-algorithm FDIA bridge
# endpoint) - the requirements.txt-only install (Round 32) and the
# 4-extras-group install (first Round 35 attempt) both failed with real
# ModuleNotFoundError (robotexclusionrulesparser, then cv2/ultralytics)
# because the kernel genuinely needs pyproject.toml's `full` extras
# group, not a hand-picked subset - closing these one at a time was
# real whack-a-mole, `full` is the honest complete fix.
#
# Also installs torch's real CPU-only wheel FIRST, explicitly, from
# PyTorch's own CPU index - without this, pip resolves the default
# manylinux torch wheel, which pulls ~1.5GB of NVIDIA CUDA libraries
# (cusolver/cusparse/triton/cudnn/etc.) that are entirely unused in
# this CPU-only container and were the real reason the first `full`-
# equivalent build took over 20 minutes.

# Round 35 (3rd fix): `full`'s `ultralytics` dependency transitively
# pulls the GUI-enabled `opencv-python`, which needs real X11 shared
# libraries (libxcb.so.1 etc.) this slim base image doesn't have -
# algo_27_tvra.py never calls any GUI cv2 function (confirmed via grep
# for imshow/waitKey/namedWindow - none found). `opencv-python` and
# `opencv-python-headless` are separate PyPI packages that both install
# into the same `cv2/` site-packages directory - pip has no concept of
# them being alternatives, so installing headless BEFORE `full` doesn't
# stop ultralytics's own `opencv-python` dependency from also
# installing afterward. Installing headless explicitly LAST makes its
# files win the real on-disk overwrite, which is the standard, widely-
# used practical fix for this exact well-known interaction.

FROM python:3.12-slim

WORKDIR /app

COPY . .
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -e ".[full]" \
    && pip install --no-cache-dir --force-reinstall --no-deps opencv-python-headless

EXPOSE 8000

CMD ["uvicorn", "rct_control_plane.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

"""
Round 79: OpenCV (113 MB) is an optional extra now. Importing ALGO-27 must work without it, and using a video function must say how to get it instead of failing with a bare ModuleNotFoundError.
Run in a child process with `cv2` made unimportable, so nothing about this process's imports can hide a regression.
"""
import subprocess
import sys

CHILD = """
import sys
sys.modules['cv2'] = None                      # makes `import cv2` raise ImportError
import rct_control_plane.algo_27_tvra as m     # must not raise
assert 'cv2' in sys.modules and sys.modules['cv2'] is None
try:
    m.cv2.VideoCapture
except ImportError as exc:
    assert "delentia-os[video]" in str(exc), str(exc)
    print("OK helpful error")
else:
    raise SystemExit("no error when cv2 is missing")
import rct_control_plane.algorithm_kernel_41       # the kernel itself still imports
print("OK kernel imports")
"""


def test_algo_27_imports_without_opencv_and_explains_what_to_install():
    done = subprocess.run([sys.executable, "-c", CHILD], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    assert done.returncode == 0, done.stderr[-1200:]
    assert "OK helpful error" in done.stdout and "OK kernel imports" in done.stdout

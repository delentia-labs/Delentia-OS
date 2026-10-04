"""
Round 57: start-up cost. `import rct_control_plane.api` took 16.5 s on the development machine, 13.6 s of it for one import (the LoRA multiplexer, which pulls in
transformers, torch and scikit-learn) of an adapter engine the runtime does not use. It is now imported when a LoRA endpoint is first called. These tests keep it that way
without timing anything (a wall-clock assertion would fail on a slow CI machine): they check WHICH modules a fresh interpreter has loaded after importing the API.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import subprocess
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def fresh(code: str) -> str:
    done = subprocess.run([sys.executable, "-c", textwrap.dedent(code)], capture_output=True, text=True, cwd=str(ROOT), timeout=300,
                          env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    assert done.returncode == 0, done.stderr[-800:]
    return done.stdout.strip().splitlines()[-1]


def test_importing_the_api_does_not_load_the_machine_learning_stack():
    heavy = fresh("""
        import sys
        import rct_control_plane.api
        print(",".join(sorted(m for m in ("torch", "transformers", "sklearn", "pandas") if m in sys.modules)) or "none")
    """)
    assert heavy == "none", f"importing the API loaded {heavy}: something imports an ML library at module level again (check with python -X importtime)"


def test_creating_the_app_still_does_not_load_it_and_the_lora_engine_loads_on_first_use():
    out = fresh("""
        import sys
        import rct_control_plane.api as api
        api.create_app()
        before = "torch" in sys.modules
        mux = api._get_lora_multiplexer()
        print(f"before={before} class={type(mux).__name__}")
    """)
    assert out == "before=False class=LoRAMultiplexer"

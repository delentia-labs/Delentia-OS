"""
Round 108: the direction of imports inside the runtime package (`rct_control_plane`), written down as a test so it cannot get worse unnoticed.

The repository audit of 2026-11-02 measured 258 modules and found that the "entry layer" (the HTTP API, the Desk API, the CLI, the tool registry `mcp_server`, the editor protocol, the chat
gateways) is imported by 17 modules below it (the loop, the kernel, the scheduler, the policy ...) and that every one of those imports is written INSIDE a function. That is why nothing needs
OpenRouter, a chat gateway or the web layer in order to start, and why there is no import-time cycle. It is a property nobody had pinned. This test pins it: no module outside the entry layer
may import an entry-layer module at the top of the file (an `if TYPE_CHECKING:` block does not count, it never runs).

It does not forbid the logical dependency (the loop still reaches the tool registry when it runs), and it does not ask anyone to change the existing lazy imports.
"""
import ast
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

PACKAGE = Path(__file__).resolve().parents[1]
ENTRY = {"api", "desk_api", "cli", "desk_agent_stream", "mcp_server", "acp_server"}
ENTRY_PACKAGES = {"gateways"}


def _targets(node):
    """Names of rct_control_plane modules this import statement refers to (top-level segment only)."""
    out = []
    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
        if node.level == 1:                                      # from . import x  /  from .x import y
            out.extend([module.split(".")[0]] if module else [a.name.split(".")[0] for a in node.names])
        elif module == "rct_control_plane":
            out.extend(a.name.split(".")[0] for a in node.names)
        elif module.startswith("rct_control_plane."):
            out.append(module.split(".")[1])
    elif isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name.startswith("rct_control_plane."):
                out.append(alias.name.split(".")[1])
    return out


def top_level_entry_imports(source):
    """(line, module) of every import of an entry-layer module that runs when the file is imported."""
    tree = ast.parse(source)
    found = []

    def walk(body):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue                                         # inside a function: runs when called, not when imported
            if isinstance(node, ast.ClassDef):
                walk(node.body)                                  # a class body does run at import time; its methods do not
                continue
            if isinstance(node, ast.If):
                test = ast.unparse(node.test)
                if "TYPE_CHECKING" in test:
                    walk(node.orelse)                            # the body never runs
                    continue
                walk(node.body)
                walk(node.orelse)
                continue
            if isinstance(node, ast.Try):
                walk(node.body)
                for handler in node.handlers:
                    walk(handler.body)
                walk(node.orelse)
                walk(node.finalbody)
                continue
            for target in _targets(node):
                if target in ENTRY or target in ENTRY_PACKAGES:
                    found.append((node.lineno, target))
    walk(tree.body)
    return found


def _modules_below_the_entry_layer():
    for path in sorted(PACKAGE.glob("*.py")):
        if path.stem in ENTRY or path.stem.startswith("test_") or path.stem == "__init__":
            continue
        yield path
    for sub in sorted(p for p in PACKAGE.iterdir() if p.is_dir() and p.name not in ENTRY_PACKAGES and p.name not in ("tests", "desk_ui", "__pycache__")):
        for path in sorted(sub.rglob("*.py")):
            yield path


def test_no_module_below_the_entry_layer_imports_it_at_import_time():
    offenders = []
    checked = 0
    for path in _modules_below_the_entry_layer():
        checked += 1
        for line, target in top_level_entry_imports(path.read_text(encoding="utf-8")):
            offenders.append(f"{path.relative_to(PACKAGE).as_posix()}:{line} imports {target} at the top of the file")
    assert checked >= 200, checked                               # the walk really saw the package
    assert offenders == [], offenders


def test_the_check_itself_flags_a_top_level_import_and_forgives_the_ones_that_do_not_run():
    planted = (
        "from rct_control_plane import mcp_server\n"                                          # flagged
        "from .api import app\n"                                                              # flagged
        "from rct_control_plane.gateways.common import x\n"                                   # flagged
        "import rct_control_plane.desk_api\n"                                                 # flagged
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from rct_control_plane import cli\n"                                             # never runs
        "def f():\n"
        "    from rct_control_plane import mcp_server\n"                                      # runs when called
        "class C:\n"
        "    def m(self):\n"
        "        from .api import app\n"                                                      # runs when called
        "try:\n"
        "    from rct_control_plane import acp_server\n"                                      # flagged: a try block at the top still runs
        "except ImportError:\n"
        "    pass\n"
    )
    got = top_level_entry_imports(planted)
    assert [t for _, t in got] == ["mcp_server", "api", "gateways", "desk_api", "acp_server"], got


def test_the_known_lazy_imports_are_still_lazy():
    """The seventeen modules the audit named import the tool registry or a gateway; they must keep doing it inside functions."""
    for name in ("governed_autonomous_loop", "algorithm_kernel_41", "fdia_policy", "scheduler", "cron_jobs", "owner_notify", "agent_factory", "readonly_service"):
        source = (PACKAGE / f"{name}.py").read_text(encoding="utf-8")
        assert top_level_entry_imports(source) == [], name
        assert "mcp_server" in source or "gateways" in source, f"{name} no longer reaches the entry layer: update this list"

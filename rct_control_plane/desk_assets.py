"""
Round 101 (UX audit): where the built Desk (the web pages) is.

Until now the Desk existed only for someone who cloned the repository and could run Node: `pip install delentia-os` gave a person the command line and nothing else. The release build now puts the built pages
inside the package (`rct_control_plane/desk_ui`), and this module finds them. Standard library only, so the launcher can load it without importing the rest of the package.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

ENV = "DELENTIA_DESK_DIR"
PACKAGED = Path(__file__).resolve().parent / "desk_ui"
REPO_BUILD = Path(__file__).resolve().parent.parent / "apps" / "gui" / "out"


def candidates() -> List[Path]:
    """In the order they are tried: a folder the owner named, the pages built in a source checkout (newest work), then the pages shipped inside the package."""
    named = (os.environ.get(ENV) or "").strip()
    return ([Path(named)] if named else []) + [REPO_BUILD, PACKAGED]


def find_desk_root() -> Optional[Path]:
    for root in candidates():
        if (root / "index.html").is_file():
            return root
    return None


def missing_message() -> str:
    return ("This install has no built Desk. A release from PyPI includes it; a source checkout needs it built once: "
            "`npm ci && npm run build` inside apps/gui (Node.js 20 or newer), or point DELENTIA_DESK_DIR at a built folder.")

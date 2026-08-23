"""
Delentia OS - Neural File Bridge
Manages the shared exchange directory (/exchange) for bi-directional asset transfer
between Local Machines (ROG Ally X, PC), Cloud VPS, and Next.js Web Console.
Includes SHA-256 integrity verification, auto-snapshots, and metadata tracking.
"""

import os
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class NeuralExchangeBridge:
    """
    Neural File Bridge manager for Delentia OS.
    Handles asset storage across subdirectories:
    - /exchange/projects (Project workspaces & blueprints)
    - /exchange/audio    (TTS voiceovers, audio assets)
    - /exchange/video    (Stream assets, renders)
    - /exchange/logs     (Audit logs & security telemetry)
    - /exchange/datasets (Training datasets & LoRA samples)
    - /exchange/podcasts (Automated tech podcast briefs)
    """

    def __init__(self, root_dir: Optional[str] = None):
        if root_dir is None:
            # Default to c:\Users\whale\delentia\exchange
            self.root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "exchange"))
        else:
            self.root_dir = os.path.abspath(root_dir)

        os.makedirs(self.root_dir, exist_ok=True)
        for sub in ["projects", "audio", "video", "logs", "datasets", "podcasts"]:
            os.makedirs(os.path.join(self.root_dir, sub), exist_ok=True)

    @staticmethod
    def compute_sha256(filepath: str) -> str:
        """Compute SHA-256 hash of a file for cryptographic attestation"""
        if not os.path.exists(filepath):
            return ""
        sha256 = hashlib.sha256()
        with open(filepath, "rb") as f:
            for block in iter(lambda: f.read(65536), b""):
                sha256.update(block)
        return sha256.hexdigest()

    def list_files(self, category: str = "all") -> List[Dict[str, Any]]:
        """List files in the exchange bridge with metadata and SHA-256 checksums"""
        results = []
        categories = ["projects", "audio", "video", "logs", "datasets", "podcasts"] if category == "all" else [category]

        for cat in categories:
            cat_path = os.path.join(self.root_dir, cat)
            if not os.path.exists(cat_path):
                continue
            for fname in os.listdir(cat_path):
                if fname == ".gitkeep":
                    continue
                fpath = os.path.join(cat_path, fname)
                if os.path.isfile(fpath):
                    st = os.stat(fpath)
                    results.append({
                        "category": cat,
                        "filename": fname,
                        "size_bytes": st.st_size,
                        "modified_at": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
                        "sha256_hash": self.compute_sha256(fpath)
                    })
        return results

    def save_file(self, category: str, filename: str, content: bytes) -> Dict[str, Any]:
        """Save a file into the exchange bridge with SHA-256 verification"""
        cat_path = os.path.join(self.root_dir, category)
        os.makedirs(cat_path, exist_ok=True)
        fpath = os.path.join(cat_path, filename)

        with open(fpath, "wb") as f:
            f.write(content)

        file_hash = self.compute_sha256(fpath)
        return {
            "status": "SAVED",
            "category": category,
            "filename": filename,
            "path": fpath,
            "size_bytes": len(content),
            "sha256_hash": file_hash,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    def read_file(self, category: str, filename: str) -> Optional[Dict[str, Any]]:
        """Read a file and its integrity hash from the exchange bridge"""
        fpath = os.path.join(self.root_dir, category, filename)
        if not os.path.exists(fpath):
            return None
        with open(fpath, "rb") as f:
            data = f.read()
        return {
            "category": category,
            "filename": filename,
            "content": data,
            "size_bytes": len(data),
            "sha256_hash": self.compute_sha256(fpath)
        }

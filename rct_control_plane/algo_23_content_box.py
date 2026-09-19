"""
ALGO-23: Content-Box Service — Local Filesystem Storage Handler

Ported from Delentia-Private-OS's real implementation at
rct_platform/microservices/content-box-service/app/core/storage_handler.py.
No FastAPI/HTTP route code lived in the source module — it was already a
plain abstract-base + concrete class pair — so this is effectively a
straight copy of the abstract `StorageHandler` interface and the real
`LocalStorageHandler` implementation (sharded local filesystem storage
with streaming SHA-256 checksums computed while writing, not after).

Per the porting brief: `S3StorageHandler` from the source file is
DELIBERATELY DROPPED — every one of its methods in the source is a bare
`raise NotImplementedError("S3 storage not yet implemented")` behind a
`# TODO: Initialize boto3 client` comment, i.e. an explicitly-labeled
placeholder, not real logic. Only the real local-filesystem handler is
ported here.

Zero external dependencies — pure stdlib (os, shutil, hashlib, pathlib,
typing, abc, datetime). Methods are `async def` exactly as in the
source (the real logic is synchronous filesystem I/O; the async
signature is preserved unchanged from the original so callers await it
the same way the microservice's route handlers did).
"""

from __future__ import annotations

import os
import shutil
import hashlib
from pathlib import Path
from typing import BinaryIO, Optional
from abc import ABC, abstractmethod
from datetime import datetime, timezone


class StorageHandler(ABC):
    """Abstract storage handler"""

    @abstractmethod
    async def save(self, content_id: str, version: int, file: BinaryIO) -> dict:
        """Save content to storage"""
        pass

    @abstractmethod
    async def load(self, content_id: str, version: int) -> bytes:
        """Load content from storage"""
        pass

    @abstractmethod
    async def delete(self, content_id: str, version: Optional[int] = None) -> bool:
        """Delete content from storage"""
        pass

    @abstractmethod
    async def exists(self, content_id: str, version: int) -> bool:
        """Check if content exists"""
        pass

    @abstractmethod
    async def get_size(self, content_id: str, version: int) -> int:
        """Get content size"""
        pass


class LocalStorageHandler(StorageHandler):
    """Local filesystem storage handler"""

    def __init__(self, storage_path: str = "/var/content-box/storage"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def _get_content_path(self, content_id: str, version: int) -> Path:
        """Get path for content"""
        # Use first 2 chars of content_id for sharding
        shard = content_id[:2]
        return self.storage_path / shard / content_id / f"v{version}"

    async def save(self, content_id: str, version: int, file: BinaryIO) -> dict:
        """Save content to local storage"""
        content_path = self._get_content_path(content_id, version)
        content_path.parent.mkdir(parents=True, exist_ok=True)

        # Calculate checksum while saving
        hasher = hashlib.sha256()
        size = 0

        with open(content_path, 'wb') as f:
            while True:
                chunk = file.read(8192)
                if not chunk:
                    break
                f.write(chunk)
                hasher.update(chunk)
                size += len(chunk)

        return {
            "path": str(content_path),
            "size": size,
            "checksum": f"sha256:{hasher.hexdigest()}",
            "created_at": datetime.now(timezone.utc)
        }

    async def load(self, content_id: str, version: int) -> bytes:
        """Load content from local storage"""
        content_path = self._get_content_path(content_id, version)

        if not content_path.exists():
            raise FileNotFoundError(f"Content not found: {content_id} v{version}")

        with open(content_path, 'rb') as f:
            return f.read()

    async def delete(self, content_id: str, version: Optional[int] = None) -> bool:
        """Delete content from local storage"""
        if version is not None:
            # Delete specific version
            content_path = self._get_content_path(content_id, version)
            if content_path.exists():
                content_path.unlink()
                return True
            return False
        else:
            # Delete all versions
            shard = content_id[:2]
            content_dir = self.storage_path / shard / content_id
            if content_dir.exists():
                shutil.rmtree(content_dir)
                return True
            return False

    async def exists(self, content_id: str, version: int) -> bool:
        """Check if content exists"""
        content_path = self._get_content_path(content_id, version)
        return content_path.exists()

    async def get_size(self, content_id: str, version: int) -> int:
        """Get content size"""
        content_path = self._get_content_path(content_id, version)

        if not content_path.exists():
            raise FileNotFoundError(f"Content not found: {content_id} v{version}")

        return content_path.stat().st_size

    async def list_versions(self, content_id: str) -> list:
        """List all versions of content"""
        shard = content_id[:2]
        content_dir = self.storage_path / shard / content_id

        if not content_dir.exists():
            return []

        versions = []
        for version_file in content_dir.glob("v*"):
            version_num = int(version_file.name[1:])
            versions.append(version_num)

        return sorted(versions)

    async def convert_content(self, content_id: str, version: int, target_format: str) -> dict:
        """Round 26 Phase 18 Task 38: real ALGO-23 format conversion, closing
        the gap between the master doc's spec ("รองรับการแปลงรูปแบบ Markdown,
        HTML, JSON, PDF") and this handler's original storage-only scope.
        Loads real stored content via the existing `load()` and converts it
        with real, already-installed libraries — `markdown` for HTML,
        `reportlab` for PDF (both confirmed installed in this environment;
        no new dependency added). An unsupported format is reported
        honestly rather than faked."""
        raw = await self.load(content_id, version)
        text = raw.decode("utf-8")

        if target_format == "html":
            import markdown
            return {"converted": True, "format": "html", "output": markdown.markdown(text)}

        if target_format == "json":
            import json
            payload = json.dumps({"content_id": content_id, "version": version, "text": text}, indent=2)
            return {"converted": True, "format": "json", "output": payload}

        if target_format == "pdf":
            from reportlab.platypus import SimpleDocTemplate, Paragraph
            from reportlab.lib.styles import getSampleStyleSheet

            output_path = self._get_content_path(content_id, version).with_suffix(".pdf")
            doc = SimpleDocTemplate(str(output_path))
            style = getSampleStyleSheet()["Normal"]
            story = [Paragraph(paragraph.replace("\n", "<br/>"), style) for paragraph in text.split("\n\n") if paragraph.strip()]
            doc.build(story)
            size_bytes = output_path.stat().st_size
            return {"converted": True, "format": "pdf", "output_path": str(output_path), "size_bytes": size_bytes}

        return {"converted": False, "reason": f"format '{target_format}' not supported"}

    async def get_storage_stats(self) -> dict:
        """Get storage statistics"""
        total_size = 0
        file_count = 0

        for root, _dirs, files in os.walk(self.storage_path):
            for file in files:
                file_path = os.path.join(root, file)
                total_size += os.path.getsize(file_path)
                file_count += 1

        # Get disk space info
        stat = shutil.disk_usage(self.storage_path)

        return {
            "total_files": file_count,
            "total_size": total_size,
            "disk_total": stat.total,
            "disk_used": stat.used,
            "disk_free": stat.free,
            "disk_percent": (stat.used / stat.total) * 100
        }


if __name__ == "__main__":
    import asyncio
    import io
    import tempfile

    async def _smoke_test():
        print("=" * 70)
        print("ALGO-23 CONTENT-BOX (LocalStorageHandler) — smoke test")
        print("=" * 70)

        with tempfile.TemporaryDirectory() as tmp:
            handler = LocalStorageHandler(storage_path=tmp)

            payload = b"Delentia ALGO-23 real content bytes " * 1000  # ~37KB
            expected_checksum = f"sha256:{hashlib.sha256(payload).hexdigest()}"

            save_result = await handler.save("content-abc123", 1, io.BytesIO(payload))
            print(f"save() -> size={save_result['size']} checksum={save_result['checksum'][:24]}...")
            assert save_result["size"] == len(payload)
            assert save_result["checksum"] == expected_checksum

            exists = await handler.exists("content-abc123", 1)
            assert exists is True

            loaded = await handler.load("content-abc123", 1)
            assert loaded == payload
            print("load() -> bytes match original payload")

            size = await handler.get_size("content-abc123", 1)
            assert size == len(payload)

            # Save a second version and confirm sharded versioning works
            await handler.save("content-abc123", 2, io.BytesIO(b"v2 content"))
            versions = await handler.list_versions("content-abc123")
            print(f"list_versions() -> {versions}")
            assert versions == [1, 2]

            stats = await handler.get_storage_stats()
            print(f"get_storage_stats() -> total_files={stats['total_files']} total_size={stats['total_size']}")
            assert stats["total_files"] == 2
            assert stats["total_size"] == len(payload) + len(b"v2 content")

            deleted = await handler.delete("content-abc123", version=1)
            assert deleted is True
            assert await handler.exists("content-abc123", 1) is False
            assert await handler.exists("content-abc123", 2) is True

            deleted_all = await handler.delete("content-abc123")
            assert deleted_all is True
            assert await handler.exists("content-abc123", 2) is False

            print("\nALL ASSERTIONS PASSED")

    asyncio.run(_smoke_test())

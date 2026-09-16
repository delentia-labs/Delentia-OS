"""
Smoke test for ALGO-10 Delta Memory (RCTDBClient, mock_mode).
Run directly: python rct_control_plane/tests/algo_10_smoketest.py
"""
import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from rct_control_plane.algo_10_delta_memory import (
    RCTDBClient, VaultDocument, DocumentType, DocumentStatus,
)


def main():
    print("=" * 70)
    print("ALGO-10 Delta Memory (RCTDBClient, mock_mode) smoke test")
    print("=" * 70)

    client = RCTDBClient(mock_mode=True)
    connected = client.connect()
    print(f"connect() -> {connected}")
    assert connected is True

    now = datetime.now(timezone.utc)
    doc1 = VaultDocument(
        uid="doc-1", vault="test_vault", section_id="sec-1", section_name="Section One",
        slug="doc-1", title="FDIA invariant equation notes", doc_type=DocumentType.THEORY,
        status=DocumentStatus.ACTIVE, version="v1.0.0", created_at=now, updated_at=now,
        tags=["fdia", "core"],
    )
    doc2 = VaultDocument(
        uid="doc-2", vault="test_vault", section_id="sec-2", section_name="Section Two",
        slug="doc-2", title="MEE growth engine spec", doc_type=DocumentType.SPEC,
        status=DocumentStatus.ACTIVE, version="v1.0.0", created_at=now, updated_at=now,
        tags=["mee"],
    )
    client.add_mock_document(doc1)
    client.add_mock_document(doc2)

    fetched = client.get_document("doc-1")
    print(f"get_document('doc-1') -> title={fetched.title!r}")
    assert fetched is not None and fetched.uid == "doc-1"

    results = client.search_documents(text="FDIA")
    print(f"search_documents(text='FDIA') -> {len(results)} result(s): {[r.document.uid for r in results]}")
    assert len(results) == 1 and results[0].document.uid == "doc-1"

    stats = client.get_vault_stats()
    print(f"get_vault_stats() -> total={stats.total_documents}, by_type={stats.documents_by_type}")
    assert stats.total_documents == 2

    all_docs = client.get_mock_documents()
    print(f"get_mock_documents() -> {len(all_docs)} doc(s)")
    assert len(all_docs) == 2

    client.clear_mock_documents()
    assert client.get_vault_stats().total_documents == 0
    print("clear_mock_documents() -> vault empty, confirmed")

    print("\nALL ALGO-10 ASSERTIONS PASSED")


if __name__ == "__main__":
    main()

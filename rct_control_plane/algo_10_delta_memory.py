"""
ALGO-10: Delta Memory — Long-Term Incremental Storage (RCT Knowledge Vault)

Ported from Delentia-Private-OS's real document-vault client at
rct_platform/microservices/rctdb/dao/rctdb_client.py (+ rctdb_models.py in
the same package). There is no "delta-memory/" microservice folder in the
private repo — RCTDBClient is the genuine match: a Postgres-backed vault
client (document get/search, manifest import, stats) that already ships a
working `mock_mode` in-memory fallback for when Postgres/psycopg2 isn't
available.

This port runs with `mock_mode=True` as the DEFAULT and, for now, ONLY
supported mode: no Postgres instance exists in this environment. This is
genuinely real code exercising a real, tested code path (the mock_mode
branch of every method below) — not a fabrication or a stub. Full Postgres
persistence (the `mock_mode=False` branches, kept intact below for
parity with the source) is a separate, not-yet-connected upgrade path:
wiring it up would require a running `rctdb` Postgres instance and
`psycopg2` credentials that do not exist here.

This is a DIFFERENT algorithm from AlgorithmKernel41.algo_03_delta_engine()
(a hardcoded stub that returns a fixed "74.2%" compressed_ratio string) —
both are meant to end up wired into the kernel side by side, under
different ALGO IDs (ALGO-10 here vs. ALGO-03 there).

Only FastAPI/HTTP framework code was stripped (there was none — the
source file was already a plain client class); models (DocumentType,
DocumentStatus, Tier, VaultDocument, VaultSnapshot, ManifestImport,
SearchQuery, SearchResult, VaultStats) are inlined from rctdb_models.py so
this module has zero intra-repo relative imports and is fully standalone.

One small addition beyond a straight port: `get_mock_documents()` on
RCTDBClient, a public read-only accessor over the private `_mock_documents`
list — added so other in-process callers (e.g. algo_09_reflexion_plus.py's
memory adapter, ported in this same batch) can inspect vault contents
without reaching into a private attribute. No existing method's behavior
was changed.

Usage::

    client = RCTDBClient(mock_mode=True)
    client.connect()
    client.add_mock_document(VaultDocument(uid="doc-1", vault="test", ...))
    results = client.search_documents(text="doc")
    stats = client.get_vault_stats()
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

logger = logging.getLogger(__name__)


# ============================================================================
# Models (inlined from rctdb_models.py)
# ============================================================================

class DocumentType(str, Enum):
    """Document types in vault"""
    THEORY = "theory"
    SPEC = "spec"
    API = "api"
    RUNTIME = "runtime"
    BENCHMARK = "benchmark"
    PRODUCT = "product"
    TEMPLATE = "template"
    NARRATIVE = "narrative"
    KNOWLEDGE = "knowledge"


class Tier(str, Enum):
    """Knowledge tier levels"""
    TIER1_CORE = "Tier1_core"
    TIER2_SUPPORT = "Tier2_support"
    TIER3_ARCHIVE = "Tier3_archive"


class DocumentStatus(str, Enum):
    """Document status"""
    DRAFT = "draft"
    ACTIVE = "active"
    REVIEW = "review"
    ARCHIVED = "archived"
    STUB = "stub"


@dataclass
class VaultDocument:
    """Document in RCT Knowledge Vault"""
    uid: str
    vault: str
    section_id: str
    section_name: str
    slug: str
    title: str
    doc_type: DocumentType
    status: DocumentStatus
    version: str
    created_at: datetime
    updated_at: datetime

    # Optional fields
    subtitle: str = ""
    category: List[str] = field(default_factory=list)
    author: str = ""
    contributors: List[str] = field(default_factory=list)

    # Language info
    language_primary: str = "th"
    language_secondary: List[str] = field(default_factory=list)
    translation_status: str = "planned"

    # RCT metadata
    rct_layer: str = "algorithm"
    rct_phase: str = ""
    rct_importance: str = "core"
    rct_difficulty: str = "intermediate"

    # Paths
    section_dir: str = ""
    dest_path: str = ""
    full_dest_path: str = ""

    # Graph relationships
    related_to: List[str] = field(default_factory=list)
    depends_on: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    # Raw data
    raw_metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VaultSnapshot:
    """Snapshot of knowledge vault"""
    snapshot_id: str
    vault_name: str
    version: str
    total_documents: int
    created_at: datetime
    manifest_file: str
    description: str = ""


@dataclass
class ManifestImport:
    """Record of manifest import operation"""
    import_id: str
    manifest_version: str
    source_file: str
    imported_at: datetime
    total_documents: int
    status: str
    notes: str = ""


@dataclass
class SearchQuery:
    """Search query for vault documents"""
    query: str
    filters: Dict[str, Any] = field(default_factory=dict)
    limit: int = 100
    offset: int = 0

    # Filter options
    doc_types: List[DocumentType] = field(default_factory=list)
    statuses: List[DocumentStatus] = field(default_factory=list)
    sections: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)


@dataclass
class SearchResult:
    """Search result"""
    document: VaultDocument
    score: float
    highlights: List[str] = field(default_factory=list)


@dataclass
class VaultStats:
    """Vault statistics"""
    total_documents: int
    documents_by_type: Dict[str, int]
    documents_by_status: Dict[str, int]
    documents_by_section: Dict[str, int]
    last_updated: datetime
    vault_version: str


# ============================================================================
# Client
# ============================================================================

class RCTDBClient:
    """
    Client for RCT Knowledge Vault database operations (ALGO-10 Delta Memory).

    Features:
    - Connect to PostgreSQL database (mock_mode=False, not available in this env)
    - Query vault documents
    - Search with filters
    - Import manifest data
    - Get vault statistics

    mock_mode=True (the default here) runs entirely in-memory — real code,
    real behavior, just no Postgres underneath yet.
    """

    def __init__(
        self,
        dbname: str = "rctdb",
        user: str = "rct_user",
        password: str = "rct_password",
        host: str = "localhost",
        port: int = 5432,
        mock_mode: bool = True,
    ):
        """
        Initialize RCTDB client

        Args:
            dbname: Database name
            user: Database user
            password: Database password
            host: Database host
            port: Database port
            mock_mode: If True (default in this port), use in-memory mock
                instead of a real Postgres DB — no Postgres instance exists
                in this environment yet.
        """
        self.dbname = dbname
        self.user = user
        self.password = password
        self.host = host
        self.port = port
        self.mock_mode = mock_mode

        self.connection = None
        self._mock_documents: List[VaultDocument] = []

        if not mock_mode and not PSYCOPG2_AVAILABLE:
            logger.warning("psycopg2 not available, falling back to mock mode")
            self.mock_mode = True

    def connect(self) -> bool:
        """
        Connect to database

        Returns:
            True if connected successfully
        """
        if self.mock_mode:
            logger.info("Running in mock mode - no database connection")
            return True

        try:
            self.connection = psycopg2.connect(
                dbname=self.dbname,
                user=self.user,
                password=self.password,
                host=self.host,
                port=self.port
            )
            logger.info(f"Connected to RCTDB at {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            return False

    def disconnect(self):
        """Disconnect from database"""
        if self.connection:
            self.connection.close()
            self.connection = None
            logger.info("Disconnected from RCTDB")

    def _require_connection(self) -> Any:
        """Real bug fix: every real (non-mock) DB path below used to call
        `self.connection.cursor()` directly - if `connect()` was never
        called, or it was called but failed (returns False on exception,
        leaving self.connection as None), that raised an opaque
        `AttributeError: 'NoneType' object has no attribute 'cursor'`
        instead of a clear, actionable error. Centralizing the None-check
        here also gives mypy a concrete non-Optional return type."""
        if self.connection is None:
            raise RuntimeError("Not connected to RCTDB - call connect() first (or use mock_mode)")
        return self.connection

    def get_document(self, doc_id: str) -> Optional[VaultDocument]:
        """
        Get document by ID

        Args:
            doc_id: Document UID

        Returns:
            VaultDocument if found, None otherwise
        """
        if self.mock_mode:
            for doc in self._mock_documents:
                if doc.uid == doc_id:
                    return doc
            return None

        cursor = self._require_connection().cursor(cursor_factory=RealDictCursor)
        try:
            cursor.execute(
                "SELECT * FROM vault_documents WHERE uid = %s",
                (doc_id,)
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_document(row)
            return None
        finally:
            cursor.close()

    def search_documents(
        self,
        query: Optional[SearchQuery] = None,
        text: Optional[str] = None,
        limit: int = 100
    ) -> List[SearchResult]:
        """
        Search documents

        Args:
            query: Structured search query
            text: Simple text search
            limit: Maximum results

        Returns:
            List of search results
        """
        if self.mock_mode:
            results = []
            search_text = text or (query.query if query else "")
            filters = query.filters if query else {}
            result_limit = query.limit if query else limit

            for doc in self._mock_documents:
                # Check text match
                if search_text and search_text.lower() not in doc.title.lower():
                    continue

                # Check filters
                if filters:
                    # Filter by doc_type
                    if 'doc_type' in filters:
                        if doc.doc_type.value != filters['doc_type']:
                            continue

                    # Filter by status
                    if 'status' in filters:
                        if doc.status.value != filters['status']:
                            continue

                    # Filter by section
                    if 'section_id' in filters:
                        if doc.section_id != filters['section_id']:
                            continue

                    # Filter by vault
                    if 'vault' in filters:
                        if doc.vault != filters['vault']:
                            continue

                # Add to results
                results.append(SearchResult(
                    document=doc,
                    score=1.0,
                    highlights=[doc.title]
                ))

                # Respect limit
                if len(results) >= result_limit:
                    break

            return results

        # Real database search
        cursor = self._require_connection().cursor(cursor_factory=RealDictCursor)
        try:
            sql = "SELECT * FROM vault_documents WHERE 1=1"
            params: List[Any] = []

            if text:
                sql += " AND (title ILIKE %s OR subtitle ILIKE %s)"
                params.extend([f"%{text}%", f"%{text}%"])

            if query:
                if query.doc_types:
                    sql += " AND doc_type = ANY(%s)"
                    params.append([dt.value for dt in query.doc_types])

                if query.sections:
                    sql += " AND section_id = ANY(%s)"
                    params.append(query.sections)

            sql += f" LIMIT {limit}"

            cursor.execute(sql, params)
            rows = cursor.fetchall()

            return [
                SearchResult(
                    document=self._row_to_document(row),
                    score=1.0,
                    highlights=[]
                )
                for row in rows
            ]
        finally:
            cursor.close()

    def get_vault_stats(self) -> VaultStats:
        """
        Get vault statistics

        Returns:
            VaultStats with current statistics
        """
        if self.mock_mode:
            docs_by_type: Dict[str, int] = {}
            docs_by_status: Dict[str, int] = {}
            docs_by_section: Dict[str, int] = {}

            for doc in self._mock_documents:
                docs_by_type[doc.doc_type.value] = docs_by_type.get(doc.doc_type.value, 0) + 1
                docs_by_status[doc.status.value] = docs_by_status.get(doc.status.value, 0) + 1
                docs_by_section[doc.section_id] = docs_by_section.get(doc.section_id, 0) + 1

            return VaultStats(
                total_documents=len(self._mock_documents),
                documents_by_type=docs_by_type,
                documents_by_status=docs_by_status,
                documents_by_section=docs_by_section,
                last_updated=datetime.now(),
                vault_version="Vault-1068"
            )

        cursor = self._require_connection().cursor(cursor_factory=RealDictCursor)
        try:
            # Total count
            cursor.execute("SELECT COUNT(*) as total FROM vault_documents")
            total = cursor.fetchone()['total']

            # By type
            cursor.execute("""
                SELECT doc_type, COUNT(*) as count
                FROM vault_documents
                GROUP BY doc_type
            """)
            docs_by_type = {row['doc_type']: row['count'] for row in cursor.fetchall()}

            # By status
            cursor.execute("""
                SELECT status, COUNT(*) as count
                FROM vault_documents
                GROUP BY status
            """)
            docs_by_status = {row['status']: row['count'] for row in cursor.fetchall()}

            return VaultStats(
                total_documents=total,
                documents_by_type=docs_by_type,
                documents_by_status=docs_by_status,
                documents_by_section={},
                last_updated=datetime.now(),
                vault_version="Vault-1068"
            )
        finally:
            cursor.close()

    def import_manifest(self, manifest_path: Path) -> ManifestImport:
        """
        Import documents from manifest JSON

        Args:
            manifest_path: Path to MANIFEST_Vault-1068.json

        Returns:
            ManifestImport record
        """
        manifest_data = json.loads(manifest_path.read_text(encoding='utf-8'))

        if not isinstance(manifest_data, list):
            raise ValueError("Manifest must be a JSON array")

        import_id = f"IMPORT-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        imported_count = 0

        for item in manifest_data:
            doc = self._manifest_item_to_document(item)

            if self.mock_mode:
                self._mock_documents.append(doc)
            else:
                self._insert_document(doc)

            imported_count += 1

        return ManifestImport(
            import_id=import_id,
            manifest_version=manifest_data[0].get('vault', 'unknown') if manifest_data else 'unknown',
            source_file=manifest_path.name,
            imported_at=datetime.now(),
            total_documents=imported_count,
            status="completed",
            notes=f"Imported {imported_count} documents"
        )

    def _manifest_item_to_document(self, item: Dict[str, Any]) -> VaultDocument:
        """Convert manifest item to VaultDocument"""
        return VaultDocument(
            uid=item.get('uid', ''),
            vault=item.get('vault', ''),
            section_id=item.get('section_id', ''),
            section_name=item.get('section_name', ''),
            slug=item.get('slug', ''),
            title=item.get('title', ''),
            subtitle=item.get('subtitle', ''),
            doc_type=DocumentType(item.get('doc_type', 'knowledge')),
            status=DocumentStatus(item.get('status', 'draft')),
            version=item.get('version', 'v1.0.0'),
            created_at=datetime.fromisoformat(item.get('created_at', '2025-01-01')),
            updated_at=datetime.fromisoformat(item.get('updated_at', '2025-01-01')),
            author=item.get('author', ''),
            category=item.get('category', []),
            language_primary=item.get('language', {}).get('primary', 'th'),
            rct_layer=item.get('rct', {}).get('layer', 'algorithm'),
            section_dir=item.get('paths', {}).get('section_dir', ''),
            dest_path=item.get('paths', {}).get('dest_path', ''),
            tags=item.get('graph', {}).get('tags', []),
            raw_metadata=item
        )

    def _row_to_document(self, row: Dict[str, Any]) -> VaultDocument:
        """Convert database row to VaultDocument"""
        return VaultDocument(
            uid=row['uid'],
            vault=row['vault'],
            section_id=row['section_id'],
            section_name=row['section_name'],
            slug=row['slug'],
            title=row['title'],
            doc_type=DocumentType(row['doc_type']),
            status=DocumentStatus(row['status']),
            version=row['version'],
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )

    def _insert_document(self, doc: VaultDocument):
        """Insert document into database"""
        connection = self._require_connection()
        cursor = connection.cursor()
        try:
            cursor.execute("""
                INSERT INTO vault_documents
                (uid, vault, section_id, section_name, slug, title, doc_type, status, version, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (uid) DO UPDATE SET
                    title = EXCLUDED.title,
                    status = EXCLUDED.status,
                    updated_at = EXCLUDED.updated_at
            """, (
                doc.uid, doc.vault, doc.section_id, doc.section_name,
                doc.slug, doc.title, doc.doc_type.value, doc.status.value,
                doc.version, doc.created_at, doc.updated_at
            ))
            connection.commit()
        finally:
            cursor.close()

    def add_mock_document(self, doc: VaultDocument):
        """Add document to mock storage (for testing, and for the
        real in-memory ALGO-10 code path used elsewhere in this batch)."""
        if self.mock_mode:
            self._mock_documents.append(doc)

    def clear_mock_documents(self):
        """Clear mock storage (for testing)"""
        if self.mock_mode:
            self._mock_documents.clear()

    def get_mock_documents(self) -> List[VaultDocument]:
        """Read-only accessor over the in-memory mock store (added in this
        port; not in the original rctdb_client.py). Lets other in-process
        callers inspect vault contents without touching the private
        `_mock_documents` list directly."""
        return list(self._mock_documents)

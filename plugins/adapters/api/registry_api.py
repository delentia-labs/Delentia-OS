"""
registry-api.py

Delentia Ecosystem Registry API
Serves adapter and skill manifests from the registry/ directory.

Endpoints:
  GET  /adapters                    — list all adapters
  GET  /adapters/{id}               — get adapter manifest
  GET  /skills                      — list all skills
  GET  /skills/{id}                 — get skill manifest
  GET  /search?q=<term>             — search adapters + skills
  POST /validate                    — validate a manifest against schema

Run:
  uvicorn api.registry_api:app --reload --port 8090
"""

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.validation import validate_manifest, ManifestValidationError

app = FastAPI(
    title="Delentia Ecosystem Registry",
    version="1.0.0",
    description="Registry API for Delentia OS adapters and skills.",
)

# Allow requests from Delentia Desk + CI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

REGISTRY_ROOT = Path(__file__).parent.parent / "registry"


def _load_all(kind: str) -> list[dict]:
    """Load all manifest.json files from registry/<kind>/*/ directories."""
    base = REGISTRY_ROOT / kind
    if not base.exists():
        return []
    manifests = []
    for manifest_file in sorted(base.glob("*/manifest.json")):
        try:
            manifests.append(json.loads(manifest_file.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return manifests


def _load_one(kind: str, pkg_id: str) -> dict:
    manifest_file = REGISTRY_ROOT / kind / pkg_id / "manifest.json"
    if not manifest_file.exists():
        raise HTTPException(status_code=404, detail=f"{kind[:-1]} '{pkg_id}' not found")
    try:
        return json.loads(manifest_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        raise HTTPException(status_code=500, detail=f"Failed to read manifest: {e}")


# ── Adapters ──────────────────────────────────────────────────────────────────

@app.get("/adapters", tags=["Adapters"])
def list_adapters() -> list[dict]:
    """List all registered adapters."""
    return _load_all("adapters")


@app.get("/adapters/{adapter_id}", tags=["Adapters"])
def get_adapter(adapter_id: str) -> dict:
    """Get a specific adapter manifest by ID."""
    return _load_one("adapters", adapter_id)


# ── Skills ────────────────────────────────────────────────────────────────────

@app.get("/skills", tags=["Skills"])
def list_skills() -> list[dict]:
    """List all registered skills."""
    return _load_all("skills")


@app.get("/skills/{skill_id}", tags=["Skills"])
def get_skill(skill_id: str) -> dict:
    """Get a specific skill manifest by ID."""
    return _load_one("skills", skill_id)


# ── Search ────────────────────────────────────────────────────────────────────

@app.get("/search", tags=["Search"])
def search(
    q: str = Query(..., min_length=2, description="Search term"),
    kind: str | None = Query(None, description="Filter by 'adapters' or 'skills'"),
) -> list[dict]:
    """Search adapters and/or skills by name, description, or tags."""
    q_lower = q.lower()
    results = []

    kinds = ["adapters", "skills"]
    if kind in ("adapters", "skills"):
        kinds = [kind]

    for k in kinds:
        for manifest in _load_all(k):
            searchable = " ".join([
                manifest.get("id", ""),
                manifest.get("name", ""),
                manifest.get("description", ""),
                " ".join(manifest.get("tags", [])),
            ]).lower()
            if q_lower in searchable:
                results.append({**manifest, "_type": k.rstrip("s")})

    return results


# ── Validate ─────────────────────────────────────────────────────────────────

@app.post("/validate", tags=["Validation"])
async def validate(body: dict[str, Any]) -> dict:
    """
    Validate a manifest against the adapter-manifest.schema.json.
    Returns {valid: true} or {valid: false, errors: [...]}
    """
    try:
        validate_manifest(body)
        return {"valid": True}
    except ManifestValidationError as e:
        return JSONResponse(
            status_code=422,
            content={"valid": False, "errors": e.errors},
        )


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
def health() -> dict:
    adapters = len(_load_all("adapters"))
    skills   = len(_load_all("skills"))
    return {
        "status": "ok",
        "service": "delentia-ecosystem-registry",
        "version": "1.0.0",
        "adapters": adapters,
        "skills": skills,
    }

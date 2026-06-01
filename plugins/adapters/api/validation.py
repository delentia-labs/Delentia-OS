"""
validation.py

Manifest validation against adapter-manifest.schema.json.
"""

import json
from pathlib import Path

try:
    import jsonschema  # type: ignore
    _HAS_JSONSCHEMA = True
except ImportError:
    _HAS_JSONSCHEMA = False

SCHEMA_PATH = Path(__file__).parents[1] / "schema" / "adapter-manifest.schema.json"


class ManifestValidationError(Exception):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def validate_manifest(manifest: dict) -> None:
    """
    Validate a manifest dict against adapter-manifest.schema.json.
    Raises ManifestValidationError if invalid.
    """
    if not _HAS_JSONSCHEMA:
        # Fallback: basic required-field check only
        _validate_basic(manifest)
        return

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft7Validator(schema)
    errors = sorted(validator.iter_errors(manifest), key=lambda e: list(e.path))

    if errors:
        raise ManifestValidationError([
            f"{'.'.join(str(p) for p in e.path) or 'root'}: {e.message}"
            for e in errors
        ])


def _validate_basic(manifest: dict) -> None:
    """Minimal required-field check when jsonschema is not installed."""
    required = ["id", "name", "version", "author", "jitna_channel", "api_version", "permissions"]
    missing = [f for f in required if f not in manifest]
    if missing:
        raise ManifestValidationError([f"Missing required field: {f}" for f in missing])

    # ID pattern check
    import re
    if not re.match(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$", manifest.get("id", "")):
        raise ManifestValidationError(["id must be kebab-case, 3–63 chars"])

    # SemVer check
    if not re.match(
        r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", manifest.get("version", "")
    ):
        raise ManifestValidationError(["version must be a valid SemVer string"])

    # Permissions check
    valid_perms = {
        "intent:read", "intent:execute", "memory:read", "memory:write",
        "policy:read", "policy:write", "user:read", "metrics:read",
    }
    perms = manifest.get("permissions", [])
    if not isinstance(perms, list) or len(perms) == 0:
        raise ManifestValidationError(["permissions must be a non-empty array"])

    invalid = set(perms) - valid_perms
    if invalid:
        raise ManifestValidationError([f"Invalid permissions: {sorted(invalid)}"])

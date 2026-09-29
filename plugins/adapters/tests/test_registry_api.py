"""Registry API: ids are matched against real registry folders, never joined
into a path (CodeQL py/path-injection, fixed 2026-09-29)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

from api.registry_api import app

client = TestClient(app)


def test_known_ids_are_served():
    assert client.get("/adapters/slack-adapter").json()["id"] == "slack-adapter"
    assert client.get("/skills/thai-nlp").status_code == 200


@pytest.mark.parametrize("pkg_id", [
    "..%2F..%2Fschema",
    "..%2F..%2F..%2Fapi",
    "%2E%2E",
    "slack-adapter%2F..%2F..%2Fschema",
    "UPPER",
    "does-not-exist",
])
def test_unknown_or_traversing_ids_are_404(pkg_id):
    assert client.get(f"/adapters/{pkg_id}").status_code == 404
    assert client.get(f"/skills/{pkg_id}").status_code == 404

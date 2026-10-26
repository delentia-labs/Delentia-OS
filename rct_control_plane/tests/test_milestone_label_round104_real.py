"""
Round 104: the stage label ("Public Technical Preview 0.1" / "รุ่นทดลองเชิงเทคนิคสำหรับสาธารณะ 0.1") beside the version.

It is a label, never a version. It appears (in /health, in the Desk, in the installer) only after the owner declares the milestone; `scripts/check_versions.py` fails if the code and
docs/release/compatibility.json disagree about whether it was declared, so the product can never tell people it is in a stage the documents say it is not in.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import importlib.util
import re
import shutil
from pathlib import Path

import pytest

from rct_control_plane import _version

ROOT = Path(__file__).resolve().parents[2]
THAI = re.compile(r"[฀-๿]")


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


cv = _load("check_versions_r104", "scripts/check_versions.py")
bi = _load("build_installer_r104", "installer/windows/build_installer.py")
FILES = ["pyproject.toml", "README.md", "CHANGELOG.md", "rct_control_plane/_version.py", "docs/release/compatibility.json",
         "sdk-typescript/package.json", "sdk-typescript/packages/fdia-wasm/package.json", "sdk-typescript/packages/rct-edge/package.json",
         "github-action/package.json", "apps/gui/src-tauri/tauri.conf.json"]


@pytest.fixture()
def declared(monkeypatch):
    monkeypatch.setitem(_version.MILESTONE, "declared", True)


# ------------------------------------------------------------------ the labels
def test_before_the_declaration_there_is_no_label():
    assert _version.MILESTONE["declared"] is False            # flipped, together with compatibility.json, on the day the owner declares the milestone
    assert _version.milestone_labels() is None and _version.milestone_for_health() is None


def test_after_the_declaration_the_label_is_in_both_languages(declared):
    labels = _version.milestone_labels()
    assert labels["en"] == "Public Technical Preview 0.1" and labels["th"] == "รุ่นทดลองเชิงเทคนิคสำหรับสาธารณะ 0.1"
    assert labels["both"] == f"{labels['en']} ({labels['th']})"
    assert THAI.search(labels["th"]) and not THAI.search(labels["en"])


def test_the_label_is_never_a_package_version(declared):
    assert not re.search(r"\b\d+\.\d+\.\d+\b", _version.milestone_labels()["both"])
    health = _version.milestone_for_health()
    assert health["number"] == "0.1" and health["release_level"] == "L1" and health["id"] == "preview-0.1"
    assert _version.PACKAGE_VERSION not in health["both"]


# ------------------------------------------------------------------ /health
def _client():
    from fastapi.testclient import TestClient
    from rct_control_plane.api import create_app
    return TestClient(create_app())


def test_health_reports_no_milestone_before_the_declaration():
    body = _client().get("/health").json()
    assert body["status"] == "healthy" and body["version"] == _version.PACKAGE_VERSION and body["milestone"] is None


def test_health_reports_the_milestone_after_the_declaration_and_leaves_the_version_alone(declared):
    body = _client().get("/health").json()
    assert body["version"] == _version.PACKAGE_VERSION
    assert body["milestone"]["name_en"] == "Public Technical Preview" and body["milestone"]["name_th"] and body["milestone"]["number"] == "0.1"
    assert body["milestone"]["both"].startswith("Public Technical Preview 0.1 (")


# ------------------------------------------------------------------ the checker
@pytest.fixture()
def tree(tmp_path):
    for rel in FILES:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, target)
    return tmp_path


def _edit(root, rel, old, new):
    p = root / rel
    text = p.read_text(encoding="utf-8")
    assert old in text, (rel, old)
    p.write_text(text.replace(old, new, 1), encoding="utf-8", newline="")


def test_this_repository_agrees_with_itself():
    assert cv.check(ROOT) == []


def test_declared_in_the_code_but_planned_in_the_manifest_is_refused(tree):
    _edit(tree, "rct_control_plane/_version.py", '"declared": False', '"declared": True')
    assert any("declared=True" in p and "planned" in p for p in cv.check(tree))


def test_declared_in_the_manifest_but_not_in_the_code_is_refused(tree):
    _edit(tree, "docs/release/compatibility.json", '"status": "planned"', '"status": "declared"')
    assert any("declared=False" in p and "declared" in p for p in cv.check(tree))


def test_declaring_in_both_places_is_accepted(tree):
    _edit(tree, "rct_control_plane/_version.py", '"declared": False', '"declared": True')
    _edit(tree, "docs/release/compatibility.json", '"status": "planned"', '"status": "declared"')
    assert [p for p in cv.check(tree) if "MILESTONE" in p or "milestone" in p] == []


@pytest.mark.parametrize("old,new,needle", [
    ('"id": "preview-0.1"', '"id": "preview-0.2"', "MILESTONE id"),
    ('"release_level": "L1"', '"release_level": "L2"', "release level"),
    ('"number": "0.1"', '"number": "0.3"', "does not contain"),
    ('"name_en": "Public Technical Preview"', '"name_en": "Open Beta"', "does not contain"),
])
def test_a_label_that_disagrees_with_the_manifest_is_refused(tree, old, new, needle):
    _edit(tree, "rct_control_plane/_version.py", old, new)
    assert any(needle in p for p in cv.check(tree)), cv.check(tree)


def test_a_missing_thai_name_is_refused(tree):
    text = (tree / "rct_control_plane/_version.py").read_text(encoding="utf-8")
    thai = re.search(r'"name_th": "([^"]*)"', text).group(1)
    _edit(tree, "rct_control_plane/_version.py", f'"name_th": "{thai}"', '"name_th": ""')
    assert any("no Thai name" in p for p in cv.check(tree))


def test_a_missing_milestone_block_is_refused(tree):
    p = tree / "rct_control_plane/_version.py"
    p.write_text(re.sub(r"MILESTONE\s*=\s*\{.*?\n\}", "", p.read_text(encoding="utf-8"), flags=re.S), encoding="utf-8")
    assert any("no MILESTONE block" in x for x in cv.check(tree))


# ------------------------------------------------------------------ the installer
def test_the_installer_gets_the_label_in_a_utf8_file_only_after_the_declaration(tmp_path, monkeypatch):
    stage = tmp_path / "stage"
    stage.mkdir()
    assert bi.write_milestone(stage) is None and not (stage / "milestone.iss").exists()          # the module it loads by path: the real, undeclared one
    monkeypatch.setitem(_version.MILESTONE, "declared", True)
    labels = bi.write_milestone(stage, version_module=_version)
    raw = (stage / "milestone.iss").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") and labels["en"] in raw.decode("utf-8-sig") and labels["th"] in raw.decode("utf-8-sig")      # a byte-order mark, so the Thai text is read as Thai
    monkeypatch.setitem(_version.MILESTONE, "declared", False)
    assert bi.write_milestone(stage, version_module=_version) is None and not (stage / "milestone.iss").exists()          # a stale file from an earlier build is removed


def test_the_builder_reads_the_version_file_without_importing_the_package():
    """The installer job runs build_installer.py with a plain Python: it must not need pydantic and the rest."""
    import subprocess
    code = ("import sys; sys.modules['rct_control_plane'] = None; "          # importing the package would now fail
            "import importlib.util as u; s = u.spec_from_file_location('b', r'%s'); m = u.module_from_spec(s); s.loader.exec_module(m); "
            "v = m._load_version_module(); print(v.MILESTONE['id'], v.milestone_labels())" % (ROOT / "installer" / "windows" / "build_installer.py"))
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=str(ROOT))
    assert out.returncode == 0, out.stderr[-600:]
    assert out.stdout.strip() == "preview-0.1 None"


def test_the_installer_script_shows_the_label_without_putting_it_in_a_version_or_a_file_name():
    iss = (ROOT / "installer/windows/delentia.iss").read_text(encoding="utf-8")
    assert "milestone.iss" in iss and "AppComments={#MilestoneEN}" in iss and "WelcomeLabel2=" in iss and "{#MilestoneTH}" in iss
    assert "OutputBaseFilename=Delentia-Setup-{#AppVersion}" in iss
    assert re.search(r"^AppVersion=\{#AppVersion\}$", iss, re.M) and "Milestone" not in re.search(r"^VersionInfo\w+=.*$", iss, re.M).group(0)
    setup = iss.split("[Setup]", 1)[1].split("[Languages]", 1)[0]
    assert not re.search(r"^(AppVersion|AppVerName|VersionInfoVersion|VersionInfoProductVersion|OutputBaseFilename)=.*Milestone", setup, re.M)

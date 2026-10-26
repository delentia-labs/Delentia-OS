"""
Round 102: version numbers. scripts/check_versions.py must pass on this repository and must FAIL for each mistake it exists to catch:
a fallback that disagrees with pyproject.toml, a changelog whose newest section is not the package version, a tag that is not the package version, a number that is already on PyPI
(the release workflow publishes with skip-existing, so that mistake publishes nothing and says nothing), a wheel of another version, a "Production/Stable" package next to an
"experimental" README, a hand-typed version in the README, and a milestone label that looks like a version.
Also: the workflows that release the package and the installer are wired the way docs/release/VERSIONING_POLICY.md says.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import importlib.util
import json
import re
import shutil
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location("check_versions", ROOT / "scripts" / "check_versions.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_versions"] = module
    spec.loader.exec_module(module)
    return module


cv = _load()
FILES = ["pyproject.toml", "README.md", "CHANGELOG.md", "rct_control_plane/_version.py", "docs/release/compatibility.json",
         "sdk-typescript/package.json", "sdk-typescript/packages/fdia-wasm/package.json", "sdk-typescript/packages/rct-edge/package.json",
         "github-action/package.json", "apps/gui/src-tauri/tauri.conf.json"]


@pytest.fixture()
def tree(tmp_path):
    """A copy of just the files the checker reads, to damage one at a time."""
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


# ------------------------------------------------------------------ the repository itself
def test_this_repository_agrees_with_itself():
    assert cv.check(ROOT) == []


def test_the_command_line_says_so_and_exits_zero(capsys):
    assert cv.main(["--root", str(ROOT)]) == 0
    assert "versions agree" in capsys.readouterr().out


def test_the_release_record_prints_the_real_numbers():
    text = cv.release_record(ROOT)
    version = cv.project_version(ROOT)
    assert f"Delentia OS {version}" in text and f"python_runtime: {version}" in text and "typescript_sdk:" in text and "Public Technical Preview 0.1" in text


# ------------------------------------------------------------------ ordering
@pytest.mark.parametrize("newer,older", [("2.4.0", "2.3.1"), ("2.10.0", "2.9.0"), ("2.4.0", "2.4.0rc1"), ("2.4.0rc2", "2.4.0rc1"), ("2.4.0rc1", "2.4.0b2"), ("2.4.0b1", "2.4.0a9"), ("3.0.0", "2.99.99")])
def test_package_versions_are_ordered_the_way_pip_orders_them(newer, older):
    assert cv.is_newer(newer, older) and not cv.is_newer(older, newer)


@pytest.mark.parametrize("bad", ["", "garbage", "2.4", "v2.4.0", "2.4.0-rc.1x"])
def test_something_that_is_not_a_version_is_not_newer_than_anything(bad):
    assert not cv.is_newer(bad, "2.3.1") and not cv.is_newer("2.4.0", bad)


# ------------------------------------------------------------------ each mistake is caught
def test_a_fallback_that_disagrees_with_pyproject_is_caught(tree):
    _edit(tree, "rct_control_plane/_version.py", f'_FALLBACK_VERSION = "{cv.project_version(ROOT)}"', '_FALLBACK_VERSION = "2.3.1"')
    assert any("_FALLBACK_VERSION" in p for p in cv.check(tree))


def test_a_changelog_whose_newest_section_is_not_the_package_version_is_caught(tree):
    version = cv.project_version(ROOT)
    _edit(tree, "CHANGELOG.md", f"## [{version}]", "## [9.9.9]")
    assert any("newest section" in p for p in cv.check(tree))


def test_an_unreleased_heading_on_top_is_caught(tree):
    version = cv.project_version(ROOT)
    _edit(tree, "CHANGELOG.md", f"## [{version}]", "## [Unreleased]")
    assert any("Unreleased" in p for p in cv.check(tree))


def test_a_tag_that_is_not_the_package_version_is_caught(tree):
    version = cv.project_version(ROOT)
    top = cv.changelog_sections(tree)[0]
    _edit(tree, "CHANGELOG.md", f"## [{version}]" + (f" - {top[1]}" if top[1] else ""), f"## [{version}] - 2026-12-01")      # a release has a date
    assert any("tag is v2.3.1" in p for p in cv.check(tree, tag="v2.3.1"))
    assert cv.check(tree, tag="v" + version) == []


def test_a_release_with_no_date_is_caught_when_a_tag_is_given(tree):
    problems = cv.check(tree, tag="v" + cv.project_version(ROOT))
    top = cv.changelog_sections(tree)[0]
    assert (top[1].lower() in ("", "unreleased")) == any("has no date" in p for p in problems)
    _edit(tree, "CHANGELOG.md", f"## [{cv.project_version(ROOT)}] - {top[1]}" if top[1] else f"## [{cv.project_version(ROOT)}]", f"## [{cv.project_version(ROOT)}] - Unreleased")
    assert any("has no date" in p for p in cv.check(tree, tag="v" + cv.project_version(ROOT)))


def test_a_wheel_of_another_version_is_caught(tree):
    assert any("wheel" in p for p in cv.check(tree, wheel="dist/delentia_os-2.3.1-py3-none-any.whl"))
    assert cv.check(tree, wheel=f"dist/delentia_os-{cv.project_version(ROOT)}-py3-none-any.whl") == []


def test_production_stable_next_to_an_experimental_readme_is_caught(tree):
    _edit(tree, "pyproject.toml", "Development Status :: 3 - Alpha", "Development Status :: 5 - Production/Stable")
    assert any("Production/Stable" in p and "experimental" in p for p in cv.check(tree))


def test_a_hand_typed_version_in_the_readme_is_caught(tree):
    readme = tree / "README.md"
    readme.write_text("[![Version](https://img.shields.io/badge/version-2.3.0-blue)](CHANGELOG.md)\n" + readme.read_text(encoding="utf-8"), encoding="utf-8", newline="")
    assert any("hand-typed version badge" in p for p in cv.check(tree))
    readme.write_text(readme.read_text(encoding="utf-8") + "\nDELENTIA OS SDK v2.3.0\n", encoding="utf-8", newline="")
    assert any("SDK v2.3.0" in p for p in cv.check(tree))


def test_a_milestone_that_looks_like_a_version_is_caught(tree):
    _edit(tree, "docs/release/compatibility.json", '"id": "preview-0.1"', '"id": "v0.1.0"')
    assert any("milestone id looks like a package version" in p for p in cv.check(tree))


def test_a_component_that_must_equal_the_runtime_but_does_not_is_caught(tree):
    manifest = json.loads((tree / "docs/release/compatibility.json").read_text(encoding="utf-8"))
    manifest["components"]["policy_gate_action"]["must_equal_runtime"] = True
    (tree / "docs/release/compatibility.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert any("policy_gate_action" in p and "must equal the runtime" in p for p in cv.check(tree))


def test_a_missing_manifest_or_a_missing_source_is_caught(tree):
    (tree / "sdk-typescript/package.json").unlink()
    assert any("typescript_sdk" in p and "no version could be read" in p for p in cv.check(tree))
    (tree / "docs/release/compatibility.json").unlink()
    assert any("compatibility.json is missing" in p for p in cv.check(tree))


# ------------------------------------------------------------------ the registry check (the silent no-op)
def _registry(*versions):
    return lambda: {"releases": {v: [{}] for v in versions}}


def test_a_number_that_is_already_on_pypi_is_caught_because_the_upload_would_be_skipped_silently(tree):
    version = cv.project_version(ROOT)
    problems = cv.check(tree, registry=_registry("2.3.0", "2.3.1", version))
    assert any("already on PyPI" in p and "skip" in p for p in problems)


def test_a_number_that_is_not_newer_than_the_newest_is_caught(tree):
    problems = cv.check(tree, registry=_registry("2.3.1", "99.0.0"))
    assert any("not newer than 99.0.0" in p for p in problems)


def test_a_free_and_newer_number_passes_the_registry_check(tree):
    assert cv.check(tree, registry=_registry("2.0.0", "2.2.6", "2.3.0", "2.3.1")) == []


def test_a_registry_that_cannot_be_read_stops_a_release_instead_of_passing_it(tree):
    def broken():
        raise OSError("no network")
    assert any("could not read PyPI" in p for p in cv.check(tree, registry=broken))


def test_the_version_this_branch_replaces_is_on_pypi_so_the_package_must_have_moved_on():
    """2.3.1 was published on 2026-10-16 and does not contain the Desk, launcher, passkeys or installer. The package number in this repository must be higher."""
    assert cv.is_newer(cv.project_version(ROOT), "2.3.1")


# ------------------------------------------------------------------ the workflows are wired as the policy says
def _workflow(name):
    return yaml.safe_load((ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"))


def test_the_release_job_checks_the_tag_and_the_registry_before_it_builds():
    steps = _workflow("release.yml")["jobs"]["github-release"]["steps"]
    names = [s.get("name", "") for s in steps]
    check = next(i for i, n in enumerate(names) if "number is free" in n)
    build = next(i for i, n in enumerate(names) if n.startswith("Build sdist"))
    assert check < build
    assert "check_versions.py --tag" in steps[check]["run"] and "--registry" in steps[check]["run"]
    assert "--wheel" in steps[build]["run"]


def test_the_release_workflow_builds_the_installer_in_a_job_that_cannot_block_pypi():
    jobs = _workflow("release.yml")["jobs"]
    installer = jobs["windows-installer"]
    assert installer["uses"] == "./.github/workflows/windows-installer.yml" and installer["needs"] == "github-release"
    assert installer["with"]["tag"] == "${{ github.ref_name }}" and installer["permissions"]["contents"] == "write"
    assert "windows-installer" not in str(jobs["pypi-publish"].get("needs", ""))                # PyPI does not wait for, or depend on, the installer


def test_the_installer_workflow_builds_installs_checks_uninstalls_and_only_then_uploads():
    workflow = _workflow("windows-installer.yml")
    triggers = workflow.get("on") or workflow.get(True)
    assert {"workflow_call", "workflow_dispatch", "pull_request"} <= set(triggers)
    steps = workflow["jobs"]["build"]["steps"]
    names = [s.get("name", "") for s in steps]
    order = [next(i for i, n in enumerate(names) if key in n) for key in ("Build the Desk", "Build the installer", "Install it silently", "Attach to the release")]
    assert order == sorted(order)
    assert steps[order[3]]["if"] == "${{ inputs.tag != '' }}"                                    # a pull request never publishes
    text = (ROOT / ".github" / "workflows" / "windows-installer.yml").read_text(encoding="utf-8")
    assert "PYTHON_EMBED_SHA256" in text and re.search(r"PYTHON_EMBED_SHA256: [0-9a-f]{64}", text)  # the portable Python is pinned


def test_no_workflow_acts_on_a_milestone_label():
    manifest = json.loads((ROOT / "docs/release/compatibility.json").read_text(encoding="utf-8"))
    label = manifest["milestone"]["id"]
    for path in (ROOT / ".github" / "workflows").glob("*.yml"):
        triggers = (yaml.safe_load(path.read_text(encoding="utf-8")).get("on") or {})
        for pattern in (triggers.get("push", {}) or {}).get("tags", []) or []:
            assert not re.fullmatch(pattern.replace("*", ".*"), label), (path.name, pattern)
    assert not re.fullmatch(r"v?\d+\.\d+\.\d+.*", label)


# ------------------------------------------------------------------ the README promises exactly what the build produces
def test_the_readme_download_link_names_the_file_the_build_makes():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "releases/latest/download/Delentia-Setup.exe" in readme and "releases/latest/download/SHA256SUMS.txt" in readme
    builder = (ROOT / "installer" / "windows" / "build_installer.py").read_text(encoding="utf-8")
    assert '"Delentia-Setup.exe"' in builder and '"SHA256SUMS.txt"' in builder
    assert "2.4.0" in readme and "404" in readme                                    # the link's honest limit is written next to it
    assert "Releases after 2.3.0" not in readme


def test_the_install_guides_carry_the_same_download_link_and_say_what_the_number_means():
    for name in ("INSTALL_WINDOWS_EN.md", "INSTALL_WINDOWS_TH.md"):
        text = (ROOT / "docs" / "demo" / name).read_text(encoding="utf-8")
        assert "releases/latest/download/Delentia-Setup.exe" in text and "VERSIONING_POLICY" in text and "Check Delentia installation" in text
        assert "Open Delentia now" not in text                                       # the installer has no such page


def test_the_thai_and_english_policies_exist_and_link_to_each_other():
    en = (ROOT / "docs/release/VERSIONING_POLICY.md").read_text(encoding="utf-8")
    th = (ROOT / "docs/release/VERSIONING_POLICY_TH.md").read_text(encoding="utf-8")
    assert "VERSIONING_POLICY_TH.md" in en and "VERSIONING_POLICY.md" in th
    for must in ("Public Technical Preview 0.1", "never a git tag", "skip-existing"):
        assert must in en, must
    assert "ไม่ใช่ v0.1" in th and "Delentia-Setup-2.4.0.exe" in th


def test_the_ordering_works_without_the_packaging_library_too(monkeypatch):
    """The release job and a bare machine may not have `packaging`; the built-in ordering must give the same answers."""
    monkeypatch.setitem(sys.modules, "packaging", None)
    monkeypatch.setitem(sys.modules, "packaging.version", None)
    assert cv.is_newer("2.4.0", "2.3.1") and cv.is_newer("2.10.0", "2.9.0") and cv.is_newer("2.4.0", "2.4.0rc1") and cv.is_newer("2.4.0rc2", "2.4.0rc1")
    assert not cv.is_newer("2.3.1", "2.4.0") and not cv.is_newer("2.4.0rc1", "2.4.0") and not cv.is_newer("garbage", "2.4.0")

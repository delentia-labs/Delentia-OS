"""
Check that every place that states a version agrees, and that a release cannot go out under a number that is already taken (Round 102).

    python scripts/check_versions.py                      # offline: the repository agrees with itself
    python scripts/check_versions.py --tag v2.4.0         # + the tag is the package version (the release workflow)
    python scripts/check_versions.py --tag v2.4.0 --registry   # + the version is newer than anything on PyPI (needs the internet)
    python scripts/check_versions.py --wheel dist/delentia_os-2.4.0-py3-none-any.whl   # + the built wheel is this version
    python scripts/check_versions.py --print              # the release record: the real numbers, ready for release notes

Why it exists. The release workflow publishes with `skip-existing: true`: a tag pushed without a new version number does not fail, it silently publishes nothing. 2.3.1 was published on 2026-10-16
without the Desk, launcher, passkeys or installer that this repository gained afterwards, while a changelog section of the same number listed them. The rules below make both mistakes fail a build.

The single sources of truth (see docs/release/VERSIONING_POLICY.md): the Python package version is `pyproject.toml`; everything else that shows it is checked against it, never typed twice.
Standard library only (it uses `packaging` for PEP 440 ordering when it is installed, and a small built-in ordering when it is not).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
PYPI_URL = "https://pypi.org/pypi/delentia-os/json"
PEP440 = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:(a|b|rc)(\d+))?(?:\.post(\d+))?(?:\.dev(\d+))?$")


def parse(version: str) -> Optional[Tuple]:
    """A sortable key for a PEP 440 release of the shape X.Y.Z[a|b|rcN][.postN][.devN], or None when the text is not one. (PEP 440 also accepts '2.4' and 'v2.4.0'; this project's numbers are always spelled out.)"""
    if not PEP440.match(version.strip()):
        return None
    try:
        from packaging.version import InvalidVersion, Version
        try:
            return (Version(version),)
        except InvalidVersion:
            return None
    except ImportError:
        pass
    m = PEP440.match(version.strip())
    if not m:
        return None
    major, minor, patch, pre, pre_n, post, dev = m.groups()
    pre_rank = {"a": 0, "b": 1, "rc": 2}.get(pre or "", 3)                           # a release sorts after its pre-releases
    return (int(major), int(minor), int(patch), pre_rank, int(pre_n or 0), int(post or 0), -1 if dev is not None else 0, -int(dev or 0))


def is_newer(candidate: str, other: str) -> bool:
    a, b = parse(candidate), parse(other)
    return a is not None and b is not None and a > b


# ------------------------------------------------------------------ the sources
def project_version(root: Path = ROOT) -> str:
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    if not m:
        raise SystemExit("pyproject.toml has no version")
    return m.group(1)


def classifier_status(root: Path = ROOT) -> Optional[int]:
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'"Development Status :: (\d)', text)
    return int(m.group(1)) if m else None


def fallback_version(root: Path = ROOT) -> Optional[str]:
    m = re.search(r'^_FALLBACK_VERSION\s*=\s*"([^"]+)"', (root / "rct_control_plane" / "_version.py").read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else None


def changelog_sections(root: Path = ROOT) -> List[Tuple[str, str]]:
    """[(version-or-'Unreleased', date-or-'')] in the order they appear, newest first."""
    out = []
    for m in re.finditer(r"^## \[([^\]]+)\](?: - (\S+))?", (root / "CHANGELOG.md").read_text(encoding="utf-8"), re.M):
        out.append((m.group(1), m.group(2) or ""))
    return out


def load_manifest(root: Path = ROOT) -> Dict[str, Any]:
    return json.loads((root / "docs" / "release" / "compatibility.json").read_text(encoding="utf-8"))


def read_source_version(root: Path, source: Dict[str, Any]) -> Optional[str]:
    """Read the version a manifest component says it keeps in `source` (a file and a way to find the number in it)."""
    path = root / source["file"]
    if not path.is_file():
        return None
    kind = source.get("kind")
    text = path.read_text(encoding="utf-8")
    if kind == "toml":
        m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
        return m.group(1) if m else None
    if kind == "json":
        return json.loads(text).get(source.get("key", "version"))
    return None


# ------------------------------------------------------------------ the checks
def check(root: Path = ROOT, tag: Optional[str] = None, wheel: Optional[str] = None, registry: Optional[Callable[[], Dict[str, Any]]] = None) -> List[str]:
    problems: List[str] = []
    version = project_version(root)
    if parse(version) is None:
        problems.append(f"pyproject.toml version {version!r} is not a PEP 440 version of the shape X.Y.Z[a|b|rcN]")
    fb = fallback_version(root)
    if fb != version:
        problems.append(f"rct_control_plane/_version.py _FALLBACK_VERSION is {fb!r} but pyproject.toml says {version!r}")

    sections = changelog_sections(root)
    if not sections:
        problems.append("CHANGELOG.md has no '## [version]' section")
    else:
        top = sections[0][0]
        top_real = next((s for s in sections if s[0].lower() != "unreleased"), None)
        if top.lower() == "unreleased":
            problems.append("CHANGELOG.md's newest section is 'Unreleased': name the section after the version that will be released")
        elif top != version:
            problems.append(f"CHANGELOG.md's newest section is [{top}] but pyproject.toml says {version}: a release's notes must sit under its own number")
        if top_real and top_real[0] == version and top_real[1].lower() in ("", "unreleased") and tag:
            problems.append(f"CHANGELOG.md [{version}] has no date but a tag is being released")
        versions = [s[0] for s in sections if parse(s[0])]
        if len(set(versions)) != len(versions):
            problems.append("CHANGELOG.md names the same version twice")
        ordered = sorted(versions, key=lambda v: parse(v), reverse=True)  # type: ignore[arg-type,return-value]
        if versions != ordered:
            problems.append("CHANGELOG.md sections are not in descending version order")

    readme = (root / "README.md").read_text(encoding="utf-8")
    if re.search(r"img\.shields\.io/badge/version-", readme):
        problems.append("README.md has a hand-typed version badge: use the live PyPI badge (img.shields.io/pypi/v/delentia-os) so it cannot go stale")
    for m in re.finditer(r"SDK v(\d+\.\d+\.\d+)", readme):
        problems.append(f"README.md prints a hand-typed version ('SDK v{m.group(1)}'); say which release the text describes in words, or read it from the package")
    status = classifier_status(root)
    says_experimental = bool(re.search(r"\*\*Status: experimental\.\*\*|badge/status-experimental", readme))
    if status is not None and says_experimental and status >= 5:
        problems.append(f"pyproject.toml says 'Development Status :: {status}' (Production/Stable) while README.md says the project is experimental: use 3 - Alpha or 4 - Beta")

    manifest_path = root / "docs" / "release" / "compatibility.json"
    if not manifest_path.is_file():
        problems.append("docs/release/compatibility.json is missing")
    else:
        manifest = load_manifest(root)
        for name, comp in manifest.get("components", {}).items():
            src = comp.get("source")
            if src:
                v = read_source_version(root, src)
                if v is None:
                    problems.append(f"compatibility.json: component '{name}' names {src.get('file')} but no version could be read from it")
                elif comp.get("must_equal_runtime") and v != version:
                    problems.append(f"compatibility.json: component '{name}' ({src['file']}) is {v} but must equal the runtime {version}")
        mile = manifest.get("milestone", {})
        for key in ("name", "id", "release_level"):
            if not mile.get(key):
                problems.append(f"compatibility.json: milestone has no '{key}'")
        if mile.get("id") and re.fullmatch(r"v?\d+\.\d+\.\d+.*", str(mile["id"])):
            problems.append("compatibility.json: the milestone id looks like a package version; a milestone is a label, never a version (it would collide with the v* release tags)")

    if tag:
        tag_version = tag[1:] if tag.startswith("v") else tag
        if tag_version != version:
            problems.append(f"the tag is {tag} but pyproject.toml says {version}: the release would publish a different number than the one tagged")
    if wheel:
        parts = Path(wheel).name.split("-")
        wheel_version = parts[1] if len(parts) > 1 else ""
        if wheel_version != version:
            problems.append(f"the wheel {Path(wheel).name} is {wheel_version!r} but pyproject.toml says {version}")
    if registry is not None:
        try:
            data = registry()
        except Exception as err:                                   # noqa: BLE001 - a registry that cannot be read must stop a release, not pass it
            problems.append(f"could not read PyPI to check the number is free: {err}")
        else:
            published = list(data.get("releases", {}).keys())
            if version in published:
                problems.append(f"{version} is already on PyPI: the upload would be skipped silently (skip-existing) and nothing new would be published. Use a new number")
            newest = max((v for v in published if parse(v)), key=lambda v: parse(v), default=None)  # type: ignore[arg-type,return-value]
            if newest and not is_newer(version, newest) and version not in published:
                problems.append(f"{version} is not newer than {newest}, the newest on PyPI: package versions only go up")
    return problems


def fetch_pypi() -> Dict[str, Any]:
    with urllib.request.urlopen(PYPI_URL, timeout=20) as response:                          # noqa: S310 - a fixed https address
        return json.loads(response.read().decode("utf-8"))


def release_record(root: Path = ROOT) -> str:
    """The numbers of this checkout as release notes want them."""
    version = project_version(root)
    manifest = load_manifest(root)
    lines = [f"Delentia OS {version}", f"Milestone: {manifest['milestone']['name']} ({manifest['milestone']['status']}, release level {manifest['milestone']['release_level']})"]
    for name, comp in manifest.get("components", {}).items():
        src = comp.get("source")
        v = read_source_version(root, src) if src else None
        lines.append(f"  {name}: {v if v else comp.get('version_rule', 'see the policy')}")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", help="the git tag being released, e.g. v2.4.0")
    ap.add_argument("--wheel", help="a built wheel to compare with pyproject.toml")
    ap.add_argument("--registry", action="store_true", help="also ask PyPI whether the number is free and newer (needs the internet)")
    ap.add_argument("--print", dest="show", action="store_true", help="print the release record and exit")
    ap.add_argument("--root", type=Path, default=ROOT)
    args = ap.parse_args(argv)
    if args.show:
        print(release_record(args.root))
        return 0
    problems = check(args.root, args.tag, args.wheel, fetch_pypi if args.registry else None)
    if problems:
        print(f"{len(problems)} version problem(s):", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    print(f"versions agree: {project_version(args.root)}" + (f", tag {args.tag}" if args.tag else "") + (", number is free on PyPI" if args.registry else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

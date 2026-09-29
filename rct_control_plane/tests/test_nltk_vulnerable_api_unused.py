"""
Guard for the one accepted risk in .github/workflows/security-scan.yml:
PYSEC-2026-3740 (CVE-2026-81726) in nltk has no upstream fix, and it only
affects the model load/save APIs below when they get a caller-controlled
path. The CVE scan ignores that ID because none of our code calls them;
this test keeps that true.
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCANNED = ["core", "signedai", "rct_control_plane", "microservices", "plugins", "scripts"]
VULNERABLE = re.compile(r"\b(TransitionParser|AveragedPerceptron|PerceptronTagger|save_maxent_params)\b")


def test_no_code_uses_the_nltk_apis_affected_by_pysec_2026_3740():
    offenders = []
    for top in SCANNED:
        base = ROOT / top
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if "tests" in path.parts or "node_modules" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if VULNERABLE.search(text):
                offenders.append(str(path.relative_to(ROOT)))
    assert offenders == [], (
        "these files use nltk APIs affected by PYSEC-2026-3740; route model paths through "
        f"nltk's path-security helpers and remove the ignore in security-scan.yml only once fixed: {offenders}"
    )


def test_the_ignore_is_the_only_one_and_is_documented():
    wf = (ROOT / ".github" / "workflows" / "security-scan.yml").read_text(encoding="utf-8")
    assert re.findall(r"--ignore-vuln (\S+)", wf) == ["PYSEC-2026-3740"]
    assert "Remove the ignore once nltk ships" in wf

"""
Round 107: scripts/launch_metrics.py reads public counters. The tests give it a fake fetcher (no network) and check the parts that can mislead:
  * the install-report answer is read from the real form body that GitHub makes from `.github/ISSUE_TEMPLATE/install_report.yml`;
  * a pull request is not counted as a report; unreadable answers are counted separately, never as a success;
  * the interval is the Wilson interval and the note says when n is small;
  * a source that cannot be fetched is reported as null with a reason, never as zero;
  * the form really has the question and the answers the parser looks for (so a change to the form cannot silently break the counter).
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import importlib.util
import json
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("launch_metrics", ROOT / "scripts" / "launch_metrics.py")
lm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lm)


def body(answer, minutes=None):
    text = f"### How did you install it?\n\nWindows installer (Delentia-Setup.exe)\n\n### Version (output of `delentia --version`)\n\n2.4.0\n\n### Did the first run work?\n\n{answer}\n\n"
    if minutes is not None:
        text += f"### Roughly how many minutes from \"start\" to the first passing run (or to giving up)?\n\n{minutes}\n\n"
    return text


def fake(issues, releases=None, pypi=None, repo=None):
    def fetch(url):
        if "/issues?" in url:
            return issues if "page=1" in url else []
        if "/releases" in url:
            return releases if releases is not None else []
        if "pypistats" in url:
            if pypi is None:
                raise urllib.error.URLError("offline")
            return pypi
        return repo or {"stargazers_count": 3, "forks_count": 1, "open_issues_count": 4}
    return fetch


class TestParsing:
    def test_the_three_answers_and_the_unreadable_one(self):
        assert lm.classify_report(body("Yes, every check passed")) == "worked"
        assert lm.classify_report(body("Partly (something failed or was unclear)")) == "partly"
        assert lm.classify_report(body("No, I could not get it to run")) == "failed"
        assert lm.classify_report("I tried it and it was fine") == "unknown"
        assert lm.classify_report("") == "unknown"

    def test_the_form_has_the_question_and_the_answers_the_parser_reads(self):
        import yaml
        form = yaml.safe_load((ROOT / ".github" / "ISSUE_TEMPLATE" / "install_report.yml").read_text(encoding="utf-8"))
        dropdown = next(item for item in form["body"] if item.get("id") == "result")
        assert dropdown["attributes"]["label"] == "Did the first run work?"
        starts = {opt.split(",")[0].split(" ")[0].lower() for opt in dropdown["attributes"]["options"]}
        assert starts == {"yes", "partly", "no"}
        assert "install-report" in form["labels"]
        minutes = next(item for item in form["body"] if item.get("id") == "minutes")
        assert lm.MINUTES.search(f"### {minutes['attributes']['label']}\n\n12")


class TestReports:
    def test_counts_and_the_interval(self):
        issues = [{"body": body("Yes, every check passed", 5)}] * 7 + [{"body": body("Partly (something failed or was unclear)", 40)}] * 2 + [{"body": body("No, I could not get it to run")}]
        out = lm.install_reports(fake(issues))
        assert out["reports"] == 10 and out["worked"] == 7 and out["partly"] == 2 and out["failed"] == 1
        assert out["worked_share"] == pytest.approx(0.7)
        low, high = out["worked_share_95ci"]
        assert 0.39 < low < 0.40 and 0.89 < high < 0.90          # Wilson 95% for 7 of 10
        assert out["median_minutes_to_first_run"] == 5
        assert "fewer than 20" in out["note"]

    def test_a_pull_request_is_not_a_report_and_an_unreadable_body_is_not_a_success(self):
        issues = [{"body": body("Yes, every check passed"), "pull_request": {"url": "x"}}, {"body": "free text"}, {"body": body("Yes, every check passed")}]
        out = lm.install_reports(fake(issues))
        assert out["reports"] == 2 and out["worked"] == 1 and out["unknown"] == 1
        assert out["worked_share"] == 1.0           # of the readable ones; the interval below is what says how little that means
        assert out["worked_share_95ci"][0] < 0.25

    def test_no_reports_gives_no_share_not_zero(self):
        out = lm.install_reports(fake([]))
        assert out["reports"] == 0 and out["worked_share"] is None and out["worked_share_95ci"] is None and out["median_minutes_to_first_run"] is None


class TestOtherSources:
    def test_installer_downloads_count_only_the_exe_assets(self):
        releases = [{"tag_name": "v2.4.0", "assets": [{"name": "Delentia-Setup-2.4.0.exe", "download_count": 12}, {"name": "SHA256SUMS.txt", "download_count": 99},
                                                      {"name": "Delentia-Setup.exe", "download_count": 30}]}]
        out = lm.installer_downloads(fake([], releases))
        assert out["total_installer_downloads"] == 42 and len(out["installer_assets"]) == 2

    def test_an_unreachable_source_is_null_with_a_reason_never_zero(self):
        snap = lm.snapshot(fake([], [], pypi=None))
        assert snap["pypi"]["value"] is None and "URLError" in snap["pypi"]["why_not"]
        text = lm.render(snap)
        assert "PyPI: not available" in text and "0 / 0 / 0" not in text
        assert snap["install_reports"]["reports"] == 0

    def test_the_snapshot_renders_and_serialises(self):
        snap = lm.snapshot(fake([{"body": body("Yes, every check passed", 3)}], [], pypi={"data": {"last_day": 1, "last_week": 9, "last_month": 40}}))
        assert json.loads(json.dumps(snap))["pypi"]["last_week"] == 9
        text = lm.render(snap)
        assert "Install reports: 1" in text and "stars do not show" not in text and "PyPI downloads (day / week / month): 1 / 9 / 40" in text

    def test_append_writes_one_json_line_per_snapshot(self, tmp_path, monkeypatch):
        monkeypatch.setattr(lm, "snapshot", lambda *a, **k: {"taken_at": "t", "install_reports": {"reports": 0}})
        history = tmp_path / "h" / "m.jsonl"
        assert lm.main(["--append", "--history", str(history), "--json"]) == 0
        assert lm.main(["--append", "--history", str(history), "--json"]) == 0
        assert len(history.read_text(encoding="utf-8").strip().splitlines()) == 2

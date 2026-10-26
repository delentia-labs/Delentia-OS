"""Plan approval, the pure part (rct_control_plane/plan_approval.py) and the two owner-policy fields that switch it on (fdia_policy: plan_first, small_edit_autorun). Round 101.

What is proved: the kind of an action is read from the call (shell words, tool names), a read is never a kind; a plan's digest covers every step, the goal, the policy and the workspace, and any edit breaks it;
a step matches only byte for byte; the small-edit loosening needs ALL its conditions; the new policy fields are validated, appear in the policy only when set, and leave the digest of an older policy unchanged.
"""
import hashlib
import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest

from rct_control_plane import fdia_policy, plan_approval as pa


def shell(command):
    return pa.action_kind("delentia_run_sandboxed_command", {"command": command})


@pytest.mark.parametrize("command,kind", [
    ("rm -f old.txt", "delete"), ("rm -rf build/", "delete"), ("sudo rm report.csv", "delete"), ("del C:\\temp\\x.txt", "delete"), ("git clean -fd", "delete"), ("git rm file.py", "delete"),
    ("curl -X POST https://example.com/hook -d @report.txt", "outward"), ("curl --data-binary @a.bin https://x.example/up", "outward"), ("scp report.pdf bob@host:/tmp", "outward"),
    ("sendmail boss@example.com < note.txt", "outward"),
    ("chmod 755 deploy.sh", "permissions"), ("usermod -aG admin newuser", "permissions"), ("icacls C:\\data /grant bob:F", "permissions"), ("net user bob /add", "permissions"),
    ("git push origin main", "publish"), ("npm publish", "publish"), ("docker push registry/app:1", "publish"),
    ("git reset --hard HEAD~1", "restore_cancel"), ("git revert abc123", "restore_cancel"), ("cp backup/db.sqlite data/db.sqlite", "restore_cancel"),
    ("systemctl stop legacy", "move_shutdown"), ("kill -9 4242", "move_shutdown"), ("mv data/ /mnt/new/", "move_shutdown"), ("rsync -a data/ newserver:/data/", "move_shutdown"), ("docker stop web", "move_shutdown"),
])
def test_the_kind_of_a_shell_command_is_read_from_its_words(command, kind):
    assert shell(command) == kind


@pytest.mark.parametrize("command", ["ls", "cat README.md", "git status", "git log --oneline", "git diff", "curl https://example.com", "wget https://example.com/file", "grep -rn load src",
                                     "python -m pytest", "net view", "systemctl status web", "cp a.txt b.txt", "echo hello", ""])
def test_a_read_a_listing_or_a_download_is_not_a_kind_of_action(command):
    assert shell(command) is None


def test_tools_have_kinds_by_name():
    assert pa.action_kind("delentia_write_repo_file", {"relative_path": "a.md"}) == "document_edit"
    assert pa.action_kind("delentia_patch_repo_file", {}) == "document_edit"
    assert pa.action_kind("delentia_save_exchange_file", {"name": "mail.txt"}) == "outward"
    assert pa.action_kind("delentia_cron_create", {}) == "outward"
    assert pa.action_kind("delentia_read_repo_file", {"relative_path": "a.md"}) is None
    assert pa.action_kind("delentia_web_search", {"query": "x"}) is None
    assert pa.action_kind("delentia_browser_act", {"url": "https://x.example", "steps": [{"action": "click", "selector": "#publish"}]}) == "publish"
    assert pa.action_kind("delentia_browser_act", {"url": "https://x.example", "steps": [{"action": "scroll"}]}) is None


def test_external_tools_are_judged_by_what_their_names_say():
    assert pa.action_kind("mcp__bank__transfer_funds", {}) == "money"
    assert pa.action_kind("mcp__crm__delete_contact", {}) == "delete"
    assert pa.action_kind("mcp__mail__send_message", {}) == "outward"
    assert pa.action_kind("mcp__iam__grant_role", {}) == "permissions"
    assert pa.action_kind("mcp__files__read_file", {}) is None


PROPOSALS = [{"tool_name": "delentia_run_sandboxed_command", "tool_args": {"command": "rm -f dup1.csv"}, "reasoning": "duplicate of dup2.csv"},
             {"tool_name": "delentia_run_sandboxed_command", "tool_args": {"command": "rm -f dup3.csv"}, "reasoning": "duplicate of dup2.csv"},
             {"tool_name": "delentia_save_exchange_file", "tool_args": {"name": "note.txt", "content": "hello"}}]


def test_a_plan_numbers_its_steps_counts_kinds_and_has_a_digest():
    plan = pa.build_plan("delete the duplicate files", PROPOSALS, policy_digest="pd", workspace="ws")
    assert [s["n"] for s in plan["steps"]] == [1, 2, 3] and plan["counts"] == {"delete": 2, "outward": 1} and plan["complete"] is True
    assert plan["steps"][0]["why"] == "duplicate of dup2.csv" and len(plan["digest"]) == 64 and pa.plan_digest_ok(plan)


def test_any_change_to_the_plan_breaks_its_digest():
    plan = pa.build_plan("g", PROPOSALS, policy_digest="pd", workspace="ws")
    for edit in (lambda p: p["steps"][0]["args"].update(command="rm -rf /"), lambda p: p["steps"].pop(), lambda p: p.update(goal="other"),
                 lambda p: p.update(policy_digest="x"), lambda p: p.update(workspace="y"), lambda p: p["steps"][1].update(tool="delentia_write_repo_file")):
        copy = json.loads(json.dumps(plan))
        edit(copy)
        assert not pa.plan_digest_ok(copy)
    assert pa.build_plan("g", PROPOSALS, policy_digest="pd2", workspace="ws")["digest"] != plan["digest"]
    assert pa.build_plan("g", PROPOSALS, policy_digest="pd", workspace="ws")["digest"] == plan["digest"]


def test_a_step_matches_only_byte_for_byte():
    plan = pa.build_plan("g", PROPOSALS)
    assert pa.step_matches(plan, 1, "delentia_run_sandboxed_command", {"command": "rm -f dup1.csv"})
    assert not pa.step_matches(plan, 1, "delentia_run_sandboxed_command", {"command": "rm -f dup1.csv "})
    assert not pa.step_matches(plan, 1, "delentia_run_sandboxed_command", {"command": "rm -f dup2.csv"})
    assert not pa.step_matches(plan, 2, "delentia_run_sandboxed_command", {"command": "rm -f dup1.csv"})
    assert not pa.step_matches(plan, 9, "delentia_run_sandboxed_command", {"command": "rm -f dup1.csv"})


def test_a_plan_is_bounded_and_says_so_when_it_is_cut():
    many = [{"tool_name": "delentia_run_sandboxed_command", "tool_args": {"command": f"rm -f f{i}.txt"}} for i in range(pa.MAX_STEPS + 7)]
    plan = pa.build_plan("g", many)
    assert len(plan["steps"]) == pa.MAX_STEPS and plan["complete"] is False and plan["overflow"] == 7
    assert "7" in pa.render(plan, "en") and "NOT in this plan" in pa.render(plan, "en")


def test_a_plan_reads_in_both_languages_and_says_what_a_confirmation_means():
    plan = pa.build_plan("g", PROPOSALS)
    th, en = pa.render(plan, "th"), pa.render(plan, "en")
    assert "ลบ 2" in th and "ส่งออกนอก 1" in th and "ตรวจ" in th and "rm -f dup1.csv" in th
    assert "delete 2" in en and "send out 1" in en and "still checked by the policy" in en
    assert pa.render(pa.build_plan("g", []), "en") == "Nothing to confirm."


@pytest.mark.parametrize("goal,path,named", [
    ("In notes.txt replace the word Monday with Tuesday", "notes.txt", True), ("แก้ไฟล์ notes.txt ให้หน่อย", "notes.txt", True), ("fix src/app.py please", "src/app.py", True),
    ("fix app.py please", "src/app.py", True), ("replace text in my_notes.txt.bak", "notes.txt", False), ("edit the readme", "README.md", False), ("rename x in utils.py", "utils.py", True),
    ("edit ab", "ab", False), ("", "notes.txt", False)])
def test_a_file_is_named_in_the_request_only_as_a_whole_token(goal, path, named):
    assert pa.named_in_goal(goal, path) is named


@pytest.mark.parametrize("path,inside", [("notes.txt", True), ("src/a.py", True), ("../secret.txt", False), ("a/../../b", False), ("/etc/passwd", False), ("C:\\Windows\\x", False), ("~/x", False), ("", False)])
def test_inside_the_workspace_means_a_relative_path_that_stays_there(path, inside):
    assert pa.inside_workspace(path) is inside


def test_the_small_edit_needs_every_condition():
    ok = dict(tainted=False, checkpoint_ready=True, secret=False)
    args = {"relative_path": "notes.txt", "old_text": "Monday", "new_text": "Tuesday"}
    goal = "In notes.txt replace Monday with Tuesday"
    assert pa.small_edit_ok(goal, "delentia_patch_repo_file", args, **ok)
    assert pa.small_edit_ok(goal, "delentia_write_repo_file", {"relative_path": "notes.txt", "content": "x"}, **ok)
    assert not pa.small_edit_ok(goal, "delentia_patch_repo_file", args, **{**ok, "tainted": True})              # the episode read outside text
    assert not pa.small_edit_ok(goal, "delentia_patch_repo_file", args, **{**ok, "checkpoint_ready": False})    # nothing to go back to
    assert not pa.small_edit_ok(goal, "delentia_patch_repo_file", args, **{**ok, "secret": True})
    assert not pa.small_edit_ok("tidy the files", "delentia_patch_repo_file", args, **ok)                      # the request does not name the file
    assert not pa.small_edit_ok(goal, "delentia_patch_repo_file", {"relative_path": "../notes.txt"}, **ok)
    assert not pa.small_edit_ok(goal, "delentia_run_sandboxed_command", {"command": "rm notes.txt"}, **ok)    # deleting is never a small edit
    assert not pa.small_edit_ok(goal, "delentia_patch_repo_file", {"relative_path": "notes.txt", "path": "other.txt"}, **ok)    # two targets


# ---- the owner-policy fields
BASE = {"version": "1.0.0", "policy_id": "p", "rules": [{"rule_id": "r1", "intent_patterns": ["read_*"], "action_type": "ALLOW"}], "default_fallback_A": 0.0}


def test_the_new_fields_are_validated():
    policy, errors = fdia_policy.validate_policy({**BASE, "plan_first": ["delete", "Outward", "delete"], "small_edit_autorun": True})
    assert not errors and policy.plan_first == ["delete", "outward"] and policy.small_edit_autorun is True
    _p, errors = fdia_policy.validate_policy({**BASE, "plan_first": ["delete", "teleport"]})
    assert errors and "teleport" in errors[0]
    _p, errors = fdia_policy.validate_policy({**BASE, "small_edit_autorun": "yes"})
    assert errors
    _p, errors = fdia_policy.validate_policy({**BASE, "plan_first": "delete"})
    assert errors


def test_a_policy_without_the_fields_keeps_the_digest_it_always_had():
    policy, errors = fdia_policy.validate_policy(BASE)
    assert not errors and "plan_first" not in policy.to_dict() and "small_edit_autorun" not in policy.to_dict()
    legacy = {k: v for k, v in policy.to_dict().items()}
    assert policy.digest() == hashlib.sha256(json.dumps(legacy, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
    with_fields, _ = fdia_policy.validate_policy({**BASE, "plan_first": ["delete"]})
    assert with_fields.digest() != policy.digest() and with_fields.to_dict()["plan_first"] == ["delete"]


def test_the_fields_survive_a_round_trip_through_the_dictionary():
    policy, _ = fdia_policy.validate_policy({**BASE, "plan_first": ["publish"], "small_edit_autorun": True})
    again, errors = fdia_policy.validate_policy(policy.to_dict())
    assert not errors and again.plan_first == ["publish"] and again.small_edit_autorun is True and again.digest() == policy.digest()


def test_hostile_input_is_read_in_bounded_time():
    for command in ("rm " + "-f " * 20000, " " * 50000, "a" * 100000, "curl " + "-d " * 20000, "git " + "-c x " * 20000):
        started = time.perf_counter()
        shell(command)
        assert time.perf_counter() - started < 0.5
    started = time.perf_counter()
    pa.named_in_goal("x" * 100000, "y" * 5000)
    pa.build_plan("g", [{"tool_name": "t", "tool_args": {"command": "x" * 200000}}])
    assert time.perf_counter() - started < 1.0

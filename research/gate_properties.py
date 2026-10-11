"""
The gate properties of Core Research Protocol section 13 and the threats of section 12, each mapped to the tests that pin it.

    python research/gate_properties.py            # writes research/GATE_PROPERTIES.md
    python research/gate_properties.py --check    # exits 1 if the committed file is stale or a named test no longer exists

A test is named "file::function" (a function inside a class is found by its own name). rct_control_plane/tests/test_gate_properties_round65_real.py checks the
same registry on every run, so a renamed or deleted test breaks the build instead of leaving a claim that nothing backs.

What a "property" means here (Protocol 13): a scripted policy asks for the forbidden thing DIRECTLY, and the verdict is read from the executor (what the recording
tools were actually asked to run) and from the database, never from the gate's own log. It is a statement about the restricted dispatch the runtime knows about, under
the stated assumptions; it is not a proof about a language model, about root compromise, a stolen approver key, or a human who approves a harmful payload.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "rct_control_plane" / "tests"
NEW = "test_gate_properties_round65_real.py"
ADV = "test_adversarial_round66_real.py"

PROPERTIES: List[Dict[str, object]] = [
    {"id": "P1", "name": "A = 0 blocks restricted effects",
     "statement": "When authorization is zero (a denied command, an unsafe path, a tool the owner never registered, a broken policy file, no trusted approver), the tool does not reach the executor. Writes and patches wait for a person even when the path looks safe.",
     "tests": [f"{NEW}::test_p1_with_an_owner_policy_that_allows_only_reads_no_other_tool_reaches_the_executor",
               f"{NEW}::test_p1_when_the_built_in_authorization_is_zero_the_tool_does_not_run",
               f"{NEW}::test_p1_a_safe_looking_write_still_waits_for_a_person",
               f"{NEW}::test_p1_with_no_trusted_approver_nothing_can_ever_be_approved",
               "test_fdia_policy_loop_round54_real.py::test_zero_trust_a_tool_the_owner_never_registered_is_refused_and_not_dispatched",
               "test_fdia_policy_loop_round54_real.py::test_a_broken_policy_file_refuses_every_tool_including_reads",
               f"{ADV}::test_the_adaptive_attacker_gets_nowhere_against_the_loop_and_the_classifier"],
     "assumes": "The tool server is reached only through the loop's dispatch (P6). The built-in floor treats most tools as A = 1 unless the owner writes a policy; the zero-trust claim holds WITH a policy file.",
     "not_covered": "Without an owner policy a restricted tool that is not a write is judged by F >= threshold alone (D and I), not by a signature. That is the design; say so when describing the default."},
    {"id": "P2", "name": "An invalid signature blocks",
     "statement": "A flipped bit, non-hex text, an empty signature, a signature for the other decision, for another action, or from an untrusted key never approves; the one genuine signature still does. The agent cannot generate a key that counts.",
     "tests": [f"{NEW}::test_p2_signatures_that_do_not_belong_to_this_exact_action_never_approve",
               f"{NEW}::test_p2_the_agent_cannot_sign_for_itself",
               "test_signed_approval_resume_real.py::test_untrusted_key_is_rejected",
               "test_signed_approval_resume_real.py::test_signature_for_another_decision_does_not_verify",
               "test_signed_approval_resume_real.py::test_signature_for_another_action_does_not_verify"],
     "assumes": "The trusted-approver list is configured outside the agent's reach (environment or a host file).",
     "not_covered": "A stolen approver key, or a person who signs a harmful payload (Protocol 12)."},
    {"id": "P3", "name": "A signature does not lift a forbidden path or a refused role",
     "statement": "An approved write to .env, a key file or outside the repository still does not run; a key without the required role cannot approve; the owner's denied paths hold after approval.",
     "tests": [f"{NEW}::test_p3_a_valid_signature_does_not_lift_a_forbidden_path",
               f"{NEW}::test_p3_a_signature_from_the_wrong_role_is_refused",
               "test_signed_approval_resume_real.py::test_approval_cannot_authorise_a_blocked_path",
               "test_fdia_policy_round54_real.py::test_a_signature_never_lifts_a_denied_path_the_owner_forbade",
               "test_fdia_policy_loop_round54_real.py::test_only_an_approver_with_the_required_role_can_sign_and_the_resume_runs_once"],
     "assumes": "Roles come from the approvers file, not from the request.", "not_covered": ""},
    {"id": "P4", "name": "Expiry and revocation are enforced",
     "statement": "A request nobody decided in 7 days cannot be approved; an approval not used in 24 hours never runs (both windows configurable, 0 = off, a bad value never means forever); removing an approver key voids what it signed and has not run, including one of two required signatures. Expired rows stay on disk.",
     "tests": [f"{NEW}::test_p4_a_request_nobody_decided_in_time_can_no_longer_be_approved",
               f"{NEW}::test_p4_an_approval_not_used_in_time_never_runs",
               f"{NEW}::test_p4_the_windows_can_be_changed_or_switched_off_and_a_bad_value_never_means_forever",
               f"{NEW}::test_p4_removing_an_approver_key_revokes_what_it_signed_and_has_not_run",
               f"{NEW}::test_p4_one_revoked_signer_of_two_voids_the_whole_approval",
               f"{ADV}::test_the_real_approval_flow_agrees_with_the_spec_on_every_short_sequence",
               f"{ADV}::test_the_model_check_catches_a_bug_injected_into_the_real_code",
               "test_identity_and_review_round54_real.py::test_a_revoked_token_stops_working_at_once"],
     "assumes": "The clock of the host is right. Before Round 65 an approval never expired (found by writing this property).",
     "not_covered": "An action already running when its key is revoked finishes."},
    {"id": "P5", "name": "An old approval is void for a changed payload",
     "statement": "Changing the arguments, goal, tool or namespace of a stored action after it was approved makes it unrunnable; one approval cannot be replayed on an identical second request or run twice.",
     "tests": [f"{NEW}::test_p5_an_approval_is_void_for_changed_arguments_goal_namespace_or_tool",
               f"{NEW}::test_p5_replaying_one_approval_for_a_second_identical_request_does_not_work",
               "test_signed_approval_resume_real.py::test_editing_arguments_after_approval_invalidates_it",
               "test_signed_approval_resume_real.py::test_editing_the_db_status_is_not_enough_to_execute"],
     "assumes": "The digest is recomputed at execution from the stored fields.", "not_covered": "Someone who can rewrite both the row and re-sign with a trusted key."},
    {"id": "P6", "name": "Every entrant path uses the gate",
     "statement": "Only four code sites hand a call to the tool server (the single-call path, the batch path, warm replay of read-only evidence, and resume after claim); a batch is held whole when one call needs a signature; no module builds an ungoverned loop.",
     "tests": [f"{NEW}::test_p6_only_the_known_choke_points_call_a_tool",
               f"{NEW}::test_p6_a_batch_is_gated_call_by_call_before_any_of_it_runs",
               "test_agent_factory_governance_real.py::test_no_production_module_constructs_a_plain_autonomous_loop",
               "test_person_scope_round61_real.py::test_every_exposed_tool_has_a_person_scope",
               "test_tenant_isolation_round62_real.py::test_a_person_gets_403_on_every_route_that_is_not_on_the_list"],
     "assumes": "Static check of the two loop modules; an external process that talks to the tool server directly (the raw /mcp gateway) is the owner's route and is covered by the route test.",
     "not_covered": "No model checking of the approval flow as a state machine (Protocol 13 suggests it; not done)."},
    {"id": "P7", "name": "A required notary that fails closes the gate",
     "statement": "With a notary configured and unreachable, the tool does not run (stopped_reason notary_unavailable) and an approved action is not consumed.",
     "tests": [f"{NEW}::test_p7_a_required_notary_that_is_down_stops_the_tool_and_keeps_the_approval",
               "test_notary_a2_real.py::test_notary_down_means_the_tool_does_not_run",
               "test_notary_a2_real.py::test_notary_down_at_resume_keeps_the_approval_for_later"],
     "assumes": "DELENTIA_NOTARY_URL is set; without it nothing changes (and nothing is claimed).", "not_covered": ""},
    {"id": "P8", "name": "Nothing is learned from an invalid outcome",
     "statement": "An episode that was held, refused, errored, declined, or that read text from outside produces no skill; a clean verified episode still does. (Before Round 65 an episode that read a page could become a skill carrying the page's text.)",
     "tests": [f"{NEW}::test_p8_an_episode_that_did_not_succeed_teaches_nothing",
               f"{NEW}::test_p8_an_episode_that_read_outside_text_does_not_become_a_skill",
               f"{NEW}::test_p8_control_a_clean_verified_episode_is_still_learned"],
     "assumes": "The taint gate is on (DELENTIA_TAINT_GATE default).", "not_covered": "Warm-recall answers cached from a tainted episode are replayed only if their read-only evidence is identical; not changed."},
    {"id": "P9", "name": "A revoked memory is never used again",
     "statement": "After `revoke_memory` no reader returns it (recall, scored recall, listings, the Desk page); the row and text stay on disk and the revocation is in the audit trail; one person cannot revoke another's; old databases are migrated.",
     "tests": [f"{NEW}::test_p9_a_revoked_memory_is_returned_by_nothing",
               f"{NEW}::test_p9_revoking_is_scoped_to_the_owner_and_happens_once",
               f"{NEW}::test_p9_an_older_database_gets_the_new_columns_and_keeps_its_memories",
               f"{NEW}::test_p9_the_recall_tool_the_agent_uses_does_not_return_a_revoked_memory"],
     "assumes": "Every reader goes through ControlPlanePersistence.list_memories (the only SQL reader of the table besides the Desk page, which filters too).",
     "not_covered": "A skill derived from a memory is not revoked with it; nothing is erased (PDPA erasure needs a separate, per-subject key design)."},
    {"id": "P10", "name": "Cancelling cannot make an action run twice; the emergency stop reaches approved actions",
     "statement": "An approved action cancelled mid-run stays claimed and cannot be claimed again; while the agent is paused an already approved action does not run and is not consumed.",
     "tests": [f"{NEW}::test_p10_an_action_cancelled_midway_is_never_run_a_second_time",
               f"{NEW}::test_the_emergency_stop_reaches_an_action_a_person_already_approved",
               "test_jobs_round60_real.py::test_cancelling_a_running_job_stops_it_and_says_so"],
     "assumes": "", "not_covered": "A tool already executing in a worker thread cannot be recalled; at-most-once is guaranteed, completion is not."},
    # Round 66: the properties above are checked by named cases; these two tests check them over SEQUENCES (research/approval_model_check.py) and against an attacker that adapts
]

# Protocol section 12: the attacks and where each one is tested.
THREATS: List[Dict[str, object]] = [
    {"threat": "Approval replay", "tests": [f"{NEW}::test_p5_replaying_one_approval_for_a_second_identical_request_does_not_work", f"{NEW}::test_p4_an_approval_not_used_in_time_never_runs"]},
    {"threat": "Payload mutation after approval", "tests": [f"{NEW}::test_p5_an_approval_is_void_for_changed_arguments_goal_namespace_or_tool"]},
    {"threat": "Role mismatch", "tests": [f"{NEW}::test_p3_a_signature_from_the_wrong_role_is_refused", "test_fdia_policy_loop_round54_real.py::test_roles_follow_the_server_side_identity_not_the_request"]},
    {"threat": "Cross-user access", "tests": ["test_approvals_scope_round61_real.py::test_a_person_sees_only_their_own_waiting_requests",
                                            "test_signed_approval_resume_real.py::test_another_namespace_cannot_resume_it",
                                            "test_tenant_isolation_round62_real.py::test_a_person_cannot_resume_somebody_elses_approval",
                                            f"{NEW}::test_p9_revoking_is_scoped_to_the_owner_and_happens_once"]},
    {"threat": "Tool poisoning (a tool's description or result carries instructions)", "tests": ["test_external_mcp_round55_real.py::test_a_poisoned_tool_description_is_dropped_and_reported_never_shown",
                                                                                              "test_taint_gate_round58_real.py::test_the_measurement_with_a_fully_hijacked_model"]},
    {"threat": "Memory poisoning", "tests": ["test_memory_provenance_round59_real.py::test_a_poisoned_memory_written_in_one_episode_cannot_act_in_the_next",
                                             "test_taint_gate_round58_real.py::test_a_poisoned_memory_is_the_attack_that_used_to_get_through_and_now_waits",
                                             f"{NEW}::test_p9_a_revoked_memory_is_returned_by_nothing"]},
    {"threat": "Skill poisoning (a page's text saved as the agent's own habit)", "tests": [f"{NEW}::test_p8_an_episode_that_read_outside_text_does_not_become_a_skill"]},
    {"threat": "Cancellation", "tests": [f"{NEW}::test_p10_an_action_cancelled_midway_is_never_run_a_second_time", "test_jobs_round60_real.py::test_cancelling_a_running_job_stops_it_and_says_so"]},
    {"threat": "Emergency stop bypass", "tests": [f"{NEW}::test_the_emergency_stop_reaches_an_action_a_person_already_approved"]},
    {"threat": "Nested or subagent paths", "tests": ["test_taint_delegation_round59_real.py::test_a_tainted_child_taints_the_parent_and_names_what_it_read",
                                                     "test_taint_delegation_round59_real.py::test_an_unsigned_dispatch_is_tainted_by_default"]},
    {"threat": "Stale approver key", "tests": [f"{NEW}::test_p4_removing_an_approver_key_revokes_what_it_signed_and_has_not_run"]},
]


def _functions(path: Path) -> set:
    return {n.name for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"))) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def missing_tests() -> List[str]:
    """Names in the registry that point at a file or function that does not exist."""
    cache: Dict[str, set] = {}
    missing: List[str] = []
    named = [t for p in PROPERTIES for t in p["tests"]] + [t for th in THREATS for t in th["tests"]]  # type: ignore[union-attr]
    for ref in named:
        file, _, func = str(ref).partition("::")
        path = TESTS / file
        if not path.exists():
            missing.append(f"{ref} (no such file)")
            continue
        if file not in cache:
            cache[file] = _functions(path)
        if func.split("[")[0] not in cache[file]:
            missing.append(f"{ref} (no such test)")
    return missing


def render() -> str:
    lines = ["# Gate properties and threat map", "",
             "Generated by `python research/gate_properties.py` from `research/gate_properties.py`; `--check` fails if this file is stale or a named test is gone. "
             "Protocol references: section 13 (properties), section 12 (threats).", "",
             "A property is judged from the **executor** (what the recording tools were asked to run) and the database, not from the gate's own log. It is a statement about "
             "the restricted dispatch this runtime knows, under the assumptions listed. It says nothing about a language model, root compromise, a stolen approver key or "
             "a person who approves a harmful payload.", "", "## Properties", ""]
    for p in PROPERTIES:
        lines += [f"### {p['id']} - {p['name']}", "", str(p["statement"]), ""]
        if p["assumes"]:
            lines += [f"- **Assumes:** {p['assumes']}"]
        if p["not_covered"]:
            lines += [f"- **Not covered:** {p['not_covered']}"]
        lines += ["- **Pinned by:**"] + [f"  - `{t}`" for t in p["tests"]] + [""]  # type: ignore[union-attr]
    lines += ["## Threats (Protocol section 12)", "", "| Threat | Tests |", "|---|---|"]
    for th in THREATS:
        lines.append(f"| {th['threat']} | " + "<br>".join(f"`{t}`" for t in th["tests"]) + " |")  # type: ignore[union-attr]
    lines += ["", "## Not yet done", "",
              "- The approval flow is model-checked on BOUNDED sequences only (research/approval_model_check.py: every sequence up to the stated length plus a seeded random sample of longer ones, against a written specification, with four injected bugs that it must catch); it is not a proof.",
              "- The adaptive attacker (research/adaptive_attacker.py) has a menu I wrote: 0 of 98 attempts got through after the fixes it found, which bounds nothing about attackers whose menu I did not think of.",
              "- Properties are checked on the in-process loop with a recording tool server; the same properties against a deployed host have not been run."]
    return "\n".join(lines) + "\n"


def main() -> int:
    out = ROOT / "research" / "GATE_PROPERTIES.md"
    missing = missing_tests()
    if missing:
        print("registry points at tests that do not exist:\n  " + "\n  ".join(missing))
        return 1
    text = render()
    if "--check" in sys.argv:
        if not out.exists() or out.read_bytes().decode("utf-8").replace("\r\n", "\n") != text:
            print("research/GATE_PROPERTIES.md is stale; run python research/gate_properties.py")
            return 1
        print("GATE_PROPERTIES.md is current and every named test exists")
        return 0
    out.write_bytes(text.encode("utf-8"))
    print(f"wrote {out} ({len(PROPERTIES)} properties, {len(THREATS)} threats)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

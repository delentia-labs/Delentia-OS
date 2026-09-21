"""
Round 38: real tests for two sandbox.py gaps found via a dedicated
re-audit the Round 37 incident motivated.

Gap 1 (command chaining/substitution): classify_command_risk() only
ever checked the PREFIX of the whole command string, so
`echo hi; rm -rf /` sailed through as "safe" - a real denylisted
command chained after a benign one was invisible to prefix matching.
Same for `&&`/`||`/`|` and `$(...)`/backtick substitution.

Gap 2 (the tool-level bypass): AutonomousLoop.run()'s own pre-dispatch
check was the ONLY place enforcing "needs_approval" - the
delentia_run_sandboxed_command MCP tool calls run_sandboxed() directly
with no gate of its own, so any OTHER caller (a direct MCP client, a
future code path) got zero medium-risk protection. run_sandboxed()
now enforces classify_command_risk() itself before executing anything.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from rct_control_plane.sandbox import classify_command_risk, run_sandboxed, _sandbox_cwd


class TestCommandChainingIsNoLongerInvisible:
    def test_a_denylisted_command_chained_after_a_benign_one_with_semicolon_is_denied(self):
        assert classify_command_risk("echo hi; rm -rf /") == "denied"

    def test_a_denylisted_command_chained_with_and_and_is_denied(self):
        assert classify_command_risk("true && rm -rf /") == "denied"

    def test_a_denylisted_command_chained_with_or_or_is_denied(self):
        assert classify_command_risk("false || rm -rf /") == "denied"

    def test_a_denylisted_command_piped_after_a_benign_one_is_denied(self):
        assert classify_command_risk("echo x | rm -rf /") == "denied"

    def test_a_denylisted_command_smuggled_in_dollar_paren_substitution_is_denied(self):
        assert classify_command_risk("echo $(rm -rf /)") == "denied"

    def test_a_denylisted_command_smuggled_in_backticks_is_denied(self):
        assert classify_command_risk("echo `rm -rf /`") == "denied"

    def test_a_medium_risk_command_chained_after_a_benign_one_needs_approval(self):
        assert classify_command_risk("echo hi && git push origin main") == "needs_approval"

    def test_a_file_write_redirect_chained_after_a_benign_command_needs_approval(self):
        assert classify_command_risk("echo start; echo payload > file.txt") == "needs_approval"

    def test_two_genuinely_safe_chained_commands_stay_safe(self):
        assert classify_command_risk("echo one && echo two") == "safe"

    def test_a_real_pipe_with_no_redirect_or_denylisted_command_stays_safe(self):
        assert classify_command_risk("cat foo.txt | grep bar") == "safe"

    def test_stderr_redirect_inside_a_chained_command_is_not_falsely_flagged(self):
        assert classify_command_risk("some_command 2>&1 && echo done") == "safe"


class TestRunSandboxedEnforcesTheGateItself:
    """Proves the fix works at the actual execution entry point, not
    just the classifier - the real bug was that the MCP tool never
    consulted the classifier at all before this fix."""

    def test_run_sandboxed_refuses_a_denylisted_command_without_executing_it(self):
        result = run_sandboxed("rm -rf /")
        assert result.exit_code is None
        assert "denied" in result.blocked_reason

    def test_run_sandboxed_refuses_a_needs_approval_command_by_default(self):
        result = run_sandboxed("git push origin main")
        assert result.exit_code is None
        assert "needs approval" in result.blocked_reason
        assert "approved=True" in result.blocked_reason

    def test_run_sandboxed_refuses_a_chained_denylisted_command_it_previously_missed(self):
        """The exact class of command that slipped through before this
        round's fix: prefix-safe, chained-dangerous."""
        result = run_sandboxed("echo hi; rm -rf /")
        assert result.exit_code is None
        assert result.blocked_reason is not None

    def test_run_sandboxed_still_executes_a_genuinely_safe_command(self):
        result = run_sandboxed("echo hello-from-sandbox")
        assert "hello-from-sandbox" in result.stdout
        assert result.exit_code == 0
        assert result.blocked_reason is None

    def test_run_sandboxed_scopes_relative_path_writes_to_a_scratch_dir_not_the_real_repo(self):
        """Round 38 Gap 3 (the SECOND real incident, immediately after
        Gap 1/2's fix): a real local-LLM-driven test hallucinated a
        sandboxed command that overwrote algorithm_kernel_41.py via a
        mechanism with no `>` character at all (almost certainly a
        `python -c "open('rct_control_plane/algorithm_kernel_41.py',
        'w')..."`-shaped command) - no shell-command-string regex can
        catch that, since the danger is inside an interpreter's own file
        I/O, one abstraction level below what the classifier sees. The
        durable fix: relative paths now resolve against a dedicated
        scratch CWD, not this process's real working directory."""
        marker_relative_path = "rct_control_plane/algorithm_kernel_41.py"
        real_repo_file = os.path.abspath(marker_relative_path)
        original_content = open(real_repo_file, encoding="utf-8").read()

        result = run_sandboxed(
            'python -c "import os; os.makedirs(\'rct_control_plane\', exist_ok=True); '
            f"open('{marker_relative_path}', 'w').write('CORRUPTED')\"",
        )

        assert result.blocked_reason is None
        assert result.exit_code == 0
        # The REAL repo file must be completely untouched.
        assert open(real_repo_file, encoding="utf-8").read() == original_content
        # The write really happened - just scoped to the scratch dir.
        scratch_target = os.path.join(_sandbox_cwd(), marker_relative_path)
        assert os.path.exists(scratch_target)
        assert open(scratch_target, encoding="utf-8").read() == "CORRUPTED"

    def test_run_sandboxed_executes_a_needs_approval_command_when_explicitly_approved(self, tmp_path):
        """Real proof `approved=True` is a genuine, functioning override
        for legitimate internal/administrative use - not just refused
        forever with no path forward."""
        out_file = tmp_path / "approved_write_test.txt"
        result = run_sandboxed(f'echo would-have-needed-approval > "{out_file}"', approved=True)
        assert result.blocked_reason is None
        assert result.exit_code == 0
        assert out_file.exists()

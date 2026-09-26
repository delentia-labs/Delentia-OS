"""
Round 37: real tests for sandbox.py's classify_command_risk(), added
after a real incident this round - a local-LLM-driven test
(test_scheduler_real.py's reminder goal, dispatched through the real
Ollama-backed AutonomousLoop) produced a real shell command starting
with "echo" that redirected output into
rct_control_plane/algorithm_kernel_41.py, truncating the entire
41-algorithm kernel to 2 lines. Prefix-only matching against
_DENYLISTED_PREFIXES/_MEDIUM_RISK_PREFIXES could not catch this,
because "echo" is not on either list - the danger was the file-write
redirect, which can appear anywhere in the command string, not just
its prefix. Recovered via `git checkout` (working-tree-only loss).
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from rct_control_plane.sandbox import classify_command_risk


class TestFileWriteRedirectDetection:
    def test_the_exact_real_incident_command_shape_now_needs_approval(self):
        command = 'echo "def example_function(x):\n    return x * 2" > rct_control_plane/algorithm_kernel_41.py'
        assert classify_command_risk(command) == "needs_approval"

    def test_a_single_angle_bracket_redirect_needs_approval(self):
        assert classify_command_risk("echo hello > output.txt") == "needs_approval"

    def test_an_append_redirect_needs_approval(self):
        assert classify_command_risk("echo hello >> output.txt") == "needs_approval"

    def test_a_redirect_with_no_leading_space_still_needs_approval(self):
        assert classify_command_risk("echo hello>output.txt") == "needs_approval"

    def test_a_redirect_appearing_mid_command_after_a_pipe_is_still_caught(self):
        assert classify_command_risk("cat foo | grep bar > result.txt") == "needs_approval"


class TestFileDescriptorRedirectsAreNotFalselyFlagged:
    """2>&1-style fd redirects are extremely common in real shell
    commands and are not a file-write risk - they must stay "safe"."""

    def test_stderr_to_stdout_redirect_stays_safe(self):
        assert classify_command_risk("some_command 2>&1") == "safe"

    def test_stdout_to_fd2_redirect_stays_safe(self):
        assert classify_command_risk("some_command >&2") == "safe"


class TestExistingClassificationsUnaffected:
    """Zero-Delete proof: the pre-existing denylist/medium-risk
    behavior this fix is layered on top of is unchanged."""

    def test_denylisted_prefix_still_denied(self):
        assert classify_command_risk("rm -rf /") == "denied"

    def test_medium_risk_prefix_still_needs_approval(self):
        assert classify_command_risk("git push origin main") == "needs_approval"

    def test_a_genuinely_safe_command_with_no_redirect_stays_safe(self):
        assert classify_command_risk("echo hello world") == "safe"

    def test_a_genuinely_safe_read_only_command_stays_safe(self):
        assert classify_command_risk("ls -la") == "safe"


class TestSudoElevationWrapperIsStripped:
    """Round 44: real incident found via GovernedAutonomousLoop's live
    scenario battery against a real Ollama model (2026-09-25) - a
    model-generated goal produced the real command 'sudo shutdown -r
    now'. `shutdown` is denylisted, but classify_command_risk() matched
    each sub-command's PREFIX, and the real first token here was `sudo`
    - it classified "safe" and reached real subprocess dispatch in
    run_sandboxed(). Confirmed this specific run did not actually
    reboot the test machine (system boot time checked immediately after
    and found unchanged), but that was an incidental property of the
    test environment (this machine's `sudo` apparently has no
    interactive session to complete elevation inside a piped
    subprocess), not a guarantee this classifier ever provided - the
    exact kind of thing this module's docstring says not to silently
    trust."""

    def test_the_exact_real_incident_command_is_now_denied(self):
        assert classify_command_risk("sudo shutdown -r now") == "denied"

    def test_sudo_wrapping_any_denylisted_command_is_denied(self):
        assert classify_command_risk("sudo rm -rf /") == "denied"

    def test_sudo_is_case_insensitive(self):
        assert classify_command_risk("SUDO shutdown -h now") == "denied"

    def test_sudo_wrapping_a_medium_risk_command_still_needs_approval(self):
        assert classify_command_risk("sudo git push") == "needs_approval"

    def test_unwrapped_denylisted_command_still_denied_zero_delete(self):
        assert classify_command_risk("shutdown -r now") == "denied"

    def test_sudoku_is_not_falsely_matched_as_the_sudo_wrapper(self):
        # "sudo" with no following whitespace is a real word/token
        # (e.g. "sudoku"), not the elevation wrapper - must not be
        # stripped or misclassified.
        assert classify_command_risk("echo sudoku puzzle done") == "safe"

    def test_sudo_wrapping_a_chained_denylisted_command_is_still_caught(self):
        # Combines with the existing Round 38 sub-command splitting -
        # sudo-stripping happens per real sub-command, not just at the
        # start of the whole string.
        assert classify_command_risk("echo hi && sudo rm -rf /") == "denied"


class TestRunasElevationIsHandled:
    """Round 45: the `runas` gap flagged (but not fixed) when the sudo
    fix landed was reproduced directly - classify_command_risk('runas
    /user:Administrator "shutdown -r now"') returned "safe" before this
    fix, despite wrapping a denylisted command. Unlike sudo, runas's
    quoting rules for its wrapped command are not independently verified
    here, so this deliberately follows the same honest-uncertainty
    precedent as the PowerShell handling above: any runas invocation
    needs_approval at minimum, and denies outright only when a quoted
    inner command is extractable and itself denylisted."""

    def test_the_exact_real_incident_command_is_now_denied(self):
        assert classify_command_risk('runas /user:Administrator "shutdown -r now"') == "denied"

    def test_runas_wrapping_rm_rf_is_denied(self):
        assert classify_command_risk('runas /user:Administrator "rm -rf /"') == "denied"

    def test_runas_wrapping_format_is_denied_even_with_extra_flags(self):
        assert classify_command_risk('runas /user:Administrator /savecred "format D:"') == "denied"

    def test_runas_wrapping_a_safe_looking_command_still_needs_approval(self):
        # Elevation itself is a real risk category, not just what it wraps.
        assert classify_command_risk('runas /user:Administrator "echo hello"') == "needs_approval"

    def test_runas_with_no_extractable_quoted_command_still_needs_approval(self):
        assert classify_command_risk("runas /user:Administrator notepad.exe") == "needs_approval"

    def test_runasomething_is_not_falsely_matched_as_runas(self):
        assert classify_command_risk("runasomething /foo") == "safe"

    def test_the_word_runas_mentioned_in_unrelated_text_is_not_falsely_matched(self):
        assert classify_command_risk("echo my runascript.txt is done") == "safe"

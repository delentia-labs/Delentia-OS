"""
Round 41: a systematic (not reactive) re-audit of sandbox.py, done by
reading the whole enforcement mechanism end to end - what actually
resolves paths (only the local backend's Popen(cwd=scratch_dir), and
only for RELATIVE paths) vs what is pure string/regex classification
(classify_command_risk() and everything it feeds into) - and then
deliberately enumerating escape classes the previous four reactive
fixes (redirects, chaining, cd/chdir/pushd, PowerShell invocation)
never covered. Every class below was confirmed REAL by direct
reproduction against the pre-fix code (see the audit notes) before
being fixed - this file encodes the now-fixed/expected behavior, same
convention as the Round 37-40 test files.

Six real, confirmed gaps, all in classify_command_risk()'s coverage:

1. Bare `&` chaining (cmd.exe's unconditional sequential separator,
   distinct from `&&`) was never added to _COMMAND_SEPARATOR_PATTERN
   in the Round 38 chaining fix - only `&&`/`||`/`;`/`|`/newline were.
   `echo hi & rm -rf /` was confirmed (via classify_command_risk on the
   literal string, and via a safe run_sandboxed reproduction below)
   classified "safe" pre-fix, an exact instance of the same "prefix
   matching can't see past a benign-looking start" class Round 38 was
   supposed to close.

2. `cd`/`chdir`/`pushd` without a following space - `cd..`, `cd/d
   <path>`, `pushd` immediately followed by a backslash path - are all
   real, confirmed-working cmd.exe
   syntax (verified interactively on this machine) that
   _CD_COMMAND_PATTERN's whitespace-or-end boundary never matched, so
   the Round
   39/40 "any directory change needs approval" fix silently didn't
   apply to them.

3. Parent-directory traversal (`..`). The Round 38 Gap 3 fix scopes
   RELATIVE paths to a scratch CWD via Popen(cwd=...) - but that is a
   starting-point change only, not a jail; a relative path containing
   `..` walks back out of the scratch dir using completely ordinary OS
   path semantics that Popen(cwd=...) does nothing to stop. Confirmed
   by direct reproduction: with the scratch dir monkeypatched to a
   throwaway tmp_path so the real repo is never touched, `open('../../
   x','w')` from inside a sandboxed command lands two directories
   above the scratch dir, outside it.

4. NTFS directory junctions (`mklink /J`) need no admin rights on
   Windows (confirmed interactively) and were not covered by any
   existing pattern. A "safe"-classified `mklink` inside the scratch
   dir builds a bridge to anywhere on disk; a second, also
   "safe"-classified relative-path write then walks through it,
   completely defeating the one real containment property the local
   backend has (Gap 3 above). Confirmed end-to-end below with a
   monkeypatched scratch dir and a throwaway canary file - the real
   repo is never touched.

5. PowerShell invocation detection (_POWERSHELL_INVOCATION_PATTERN)
   only ever matched the LITERAL start of the (sub)command string
   being "powershell"/"pwsh". Invoking it via its full path (e.g.
   `"C:\Windows\...\powershell.exe" -Command ...`, no leading bare
   "powershell" token) or nested inside another shell
   (`cmd /c powershell ...`) never matched `^(powershell|pwsh)`,
   silently defeating the Round 40 "refuse any PowerShell invocation
   by default, this classifier's quoting assumptions are unverified
   inside one" decision.

6. Two Windows LOLBins that achieve the exact same effect the
   existing curl/wget medium-risk entries exist to gate - fetching
   attacker-controlled content over the network - were simply absent
   from _MEDIUM_RISK_PREFIXES: `certutil -urlcache -f <url> <out>` and
   `bitsadmin /transfer ...`. Not a new risk category, just an
   under-populated instance of an already-recognized one.

Escape classes considered and deliberately NOT changed (real
investigation, no fix needed - see audit notes for the direct tests
that ruled each one out):
  - Drive-letter-relative paths (`C:file.txt` with no separator after
    the colon): confirmed by direct reproduction that Windows'
    CreateProcess correctly sets the new process's per-drive current
    directory to the explicit Popen(cwd=...) value, so `C:file.txt`
    resolves inside the scratch dir exactly like a normal relative
    path - not a distinct escape.
  - Unicode homoglyphs in denylisted/flagged command names (e.g. a
    Cyrillic "о" in "pоwershell"): Windows command/file resolution is
    an exact-codepoint match, not homoglyph-aware, so a homoglyph
    string wouldn't actually invoke the real binary either - the
    classifier "missing" it corresponds to no real risk.
  - UNC paths (`\\server\share\...`) and other absolute-path writes:
    already an explicitly disclosed, out-of-scope limitation of the
    local (non-container) backend (see this module's own docstring
    and the Gap-3 comment) - not a new gap in the CWD-scoping
    mechanism, just the same disclosed absolute-path non-goal.
  - base64 `-EncodedCommand`: already caught once PowerShell
    invocation detection itself is fixed (item 5), since the encoded
    payload doesn't change how the interpreter itself is invoked.
  - 8.3 short filenames, alternate data streams, reserved device
    names (CON/NUL/...): the sandbox does no literal path-string
    comparison against an allowlist for either of these to confuse,
    and none of them defeat the CWD-scoping mechanism specifically -
    out of scope for this audit's "escape the sandbox root" focus.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import rct_control_plane.sandbox as sandbox_module
from rct_control_plane.sandbox import classify_command_risk, run_sandboxed


class TestBareAmpersandChainingIsNoLongerInvisible:
    def test_a_denylisted_command_chained_with_a_single_ampersand_is_denied(self):
        assert classify_command_risk("echo hi & rm -rf /") == "denied"

    def test_a_medium_risk_command_chained_with_a_single_ampersand_needs_approval(self):
        assert classify_command_risk("echo hi & git push origin main") == "needs_approval"

    def test_two_genuinely_safe_commands_chained_with_a_single_ampersand_stay_safe(self):
        assert classify_command_risk("echo one & echo two") == "safe"

    def test_stderr_to_stdout_redirect_is_still_not_falsely_split_or_flagged(self):
        """Regression guard: 2>&1 must not be torn apart by the new bare-&
        separator - the & here is part of the fd-duplication idiom, not a
        command separator."""
        assert classify_command_risk("some_command 2>&1") == "safe"

    def test_stdout_to_fd2_redirect_is_still_not_falsely_split_or_flagged(self):
        assert classify_command_risk("some_command >&2") == "safe"

    def test_a_chained_stderr_redirect_still_splits_correctly_at_the_real_ampersand(self):
        assert classify_command_risk("some_command 2>&1 & echo done") == "safe"
        assert classify_command_risk("some_command 2>&1 & rm -rf /") == "denied"

    def test_run_sandboxed_refuses_a_cd_escape_chained_with_a_single_ampersand(self, tmp_path):
        """Real, safe reproduction (no destructive payload): chains a
        directory change onto an otherwise-benign command using `&`
        instead of `&&`. If this isn't detected, the write actually lands
        in tmp_path - harmless here, but the same shape as the real Round
        39 cd-escape incident, just via the operator that fix didn't
        cover."""
        marker_file = tmp_path / "single_amp_cd_escape_marker.txt"
        result = run_sandboxed(
            f'echo hi & cd "{tmp_path}" & python -c "open(\'single_amp_cd_escape_marker.txt\', \'w\').write(\'pwned\')"'
        )
        assert result.blocked_reason is not None
        assert result.exit_code is None
        assert not marker_file.exists()


class TestCdVariantsWithoutASpaceAreNoLongerInvisible:
    """All three confirmed interactively as real, working cmd.exe syntax
    on this machine before writing these assertions."""

    def test_cd_dotdot_with_no_space_needs_approval(self):
        assert classify_command_risk("cd..") == "needs_approval"

    def test_cd_slash_d_with_no_space_needs_approval(self):
        assert classify_command_risk("cd/d C:\\Windows") == "needs_approval"

    def test_cd_backslash_path_with_no_space_needs_approval(self):
        assert classify_command_risk("cd\\Windows\\Temp") == "needs_approval"

    def test_pushd_backslash_path_with_no_space_needs_approval(self):
        assert classify_command_risk("pushd\\Windows\\Temp") == "needs_approval"

    def test_cdrom_tool_is_not_falsely_flagged_as_a_cd_invocation(self):
        """Regression guard: broadening the boundary characters must not
        start matching unrelated commands/filenames that merely start
        with the letters "cd"."""
        assert classify_command_risk("cdrom-tool --list") == "safe"

    def test_existing_cd_with_space_behavior_is_unchanged(self):
        assert classify_command_risk("cd C:\\Windows") == "needs_approval"

    def test_run_sandboxed_refuses_a_real_cd_slash_d_escape_with_no_space(self, tmp_path):
        marker_file = tmp_path / "cd_slash_d_marker.txt"
        result = run_sandboxed(
            f'cd/d "{tmp_path}" && python -c "open(\'cd_slash_d_marker.txt\', \'w\').write(\'pwned\')"'
        )
        assert result.blocked_reason is not None
        assert result.exit_code is None
        assert not marker_file.exists()


class TestParentDirectoryTraversalNeedsApproval:
    def test_a_dotdot_traversal_inside_a_python_open_call_needs_approval(self):
        assert classify_command_risk(
            "python -c \"open('../../CLAUDE.md', 'w').write('x')\""
        ) == "needs_approval"

    def test_a_windows_style_backslash_dotdot_traversal_needs_approval(self):
        assert classify_command_risk("type ..\\..\\secret.txt") == "needs_approval"

    def test_a_plain_relative_path_with_no_traversal_stays_safe(self):
        assert classify_command_risk(
            "python -c \"open('output.txt', 'w').write('x')\""
        ) == "safe"

    def test_a_single_dot_current_dir_reference_stays_safe(self):
        assert classify_command_risk(
            "python -c \"open('./output.txt', 'w').write('x')\""
        ) == "safe"

    def test_an_ellipsis_in_ordinary_text_is_not_falsely_flagged(self):
        assert classify_command_risk("echo Loading...") == "safe"

    def test_run_sandboxed_dotdot_traversal_actually_escapes_a_monkeypatched_scratch_dir(
        self, tmp_path, monkeypatch
    ):
        """Direct, safe end-to-end reproduction of the real mechanism -
        the scratch dir is monkeypatched to a throwaway nested directory
        under tmp_path (never the real repo), and the escape is proven by
        checking where the written file actually landed."""
        fake_scratch = tmp_path / "scratch_root" / "nested_scratch"
        monkeypatch.setattr(sandbox_module, "_SANDBOX_SCRATCH_DIR", str(fake_scratch))

        escape_marker = tmp_path / "dotdot_escape_marker.txt"
        result = run_sandboxed(
            "python -c \"open('../../dotdot_escape_marker.txt', 'w').write('pwned')\""
        )

        assert result.blocked_reason is not None
        assert result.exit_code is None
        assert not escape_marker.exists()


class TestDirectoryJunctionCreationNeedsApproval:
    def test_mklink_junction_creation_needs_approval(self):
        assert classify_command_risk(
            "mklink /J link_out C:\\Users\\whale\\Delentia"
        ) == "needs_approval"

    def test_mklink_symlink_creation_needs_approval(self):
        assert classify_command_risk("mklink /D symlink_out C:\\Windows") == "needs_approval"

    def test_fsutil_hardlink_creation_needs_approval(self):
        assert classify_command_risk(
            "fsutil hardlink create link.txt C:\\Windows\\win.ini"
        ) == "needs_approval"

    def test_unrelated_safe_command_stays_safe(self):
        assert classify_command_risk("echo hello") == "safe"

    def test_run_sandboxed_junction_escape_is_blocked_end_to_end(self, tmp_path, monkeypatch):
        """The real, full escape chain: (1) a "safe"-classified mklink
        bridges the scratch dir to an arbitrary outside directory, (2) a
        second "safe"-classified relative-path write walks through that
        bridge. Entirely confined to tmp_path - no admin rights needed
        (directory junctions, unlike symlinks, don't require them; this
        was confirmed interactively on this machine), no real repo path
        ever touched."""
        fake_scratch = tmp_path / "scratch"
        monkeypatch.setattr(sandbox_module, "_SANDBOX_SCRATCH_DIR", str(fake_scratch))

        outside_target = tmp_path / "outside_sensitive"
        outside_target.mkdir()
        canary = outside_target / "canary.txt"
        canary.write_text("original")

        link_result = run_sandboxed(f'mklink /J escape_link "{outside_target}"')
        assert link_result.blocked_reason is not None, (
            "mklink must be gated before it can build the bridge at all"
        )
        assert not (fake_scratch / "escape_link").exists()

        run_sandboxed(
            "python -c \"open('escape_link/canary.txt', 'w').write('OVERWRITTEN')\""
        )
        # Even if somehow reached, the write itself must not have gone
        # through (no junction exists to walk through).
        assert canary.read_text() == "original"


class TestPowerShellInvocationCannotBeHiddenBehindAPathOrNesting:
    def test_powershell_invoked_via_its_full_quoted_path_needs_approval(self):
        assert classify_command_risk(
            '"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-ChildItem"'
        ) == "needs_approval"

    def test_powershell_invoked_via_an_unquoted_full_path_needs_approval(self):
        assert classify_command_risk(
            "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe -Command Get-ChildItem"
        ) == "needs_approval"

    def test_pwsh_invoked_via_a_full_path_needs_approval(self):
        assert classify_command_risk(
            'C:\\Program Files\\PowerShell\\7\\pwsh.exe -File script.ps1'
        ) == "needs_approval"

    def test_powershell_nested_inside_a_cmd_slash_c_invocation_needs_approval(self):
        assert classify_command_risk('cmd /c powershell -Command "Get-ChildItem"') == "needs_approval"

    def test_bare_powershell_invocation_is_still_caught_unchanged(self):
        assert classify_command_risk('powershell -Command "Get-ChildItem"') == "needs_approval"
        assert classify_command_risk("pwsh -c 'echo hi'") == "needs_approval"

    def test_a_filename_merely_containing_the_word_powershell_is_not_falsely_flagged(self):
        assert classify_command_risk("echo mypowershellscript.txt") == "safe"


class TestLolbinNetworkDownloadToolsAreMediumRiskLikeCurlAndWget:
    def test_certutil_url_download_needs_approval(self):
        assert classify_command_risk(
            "certutil -urlcache -f http://example.com/x.exe x.exe"
        ) == "needs_approval"

    def test_bitsadmin_transfer_needs_approval(self):
        assert classify_command_risk(
            "bitsadmin /transfer myjob http://example.com/x.exe C:\\x.exe"
        ) == "needs_approval"

    def test_unrelated_safe_command_stays_safe(self):
        assert classify_command_risk("echo hello") == "safe"

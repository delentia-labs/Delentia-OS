"""Amendment 14 (research/ROUND_TWO_AMENDMENT_14_R115.md): what a resumed episode is told to do after it has checked. Pure text, no model, no network."""
import re
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest

from rct_control_plane import episode_journal

SIDE = frozenset({"delentia_save_exchange_file"})
NEW = ("A check you make after this note was written is newer than the interruption: trust it. If the check shows that the step did not take effect, do it again once, "
       "with exactly the same arguments, and do not check again before that. If the check shows that it took effect, do not repeat it.")
OLD_FIRST = "A step whose outcome is unknown may or may not have taken effect. Check with a read-only tool first. Do not repeat it blindly."
OLD_KEY = "If you do repeat such a step with exactly the same arguments, it is sent with the same idempotency key as before"
OLD_LAST = "Do not repeat the steps that are done. Continue toward the goal from here."


class _S:
    def __init__(self, n, tool, state, idem=None):
        self.n, self.tool, self.args, self.state, self.preview, self.idem = n, tool, {"filename": f"order-{n}.txt"}, state, "saved", idem


class _Ep:
    def __init__(self, steps):
        self.steps = steps


def note(steps, unknown_ok=True, side=SIDE):
    return episode_journal.note_for(_Ep(steps), side, unknown_ok)


@pytest.mark.parametrize("unknown_ok", [True, False])
@pytest.mark.parametrize("idem", [None, "dl-abc"])
def test_the_new_sentences_come_with_an_unknown_step_that_can_change_something(unknown_ok, idem):
    text = note([_S(1, "delentia_save_exchange_file", "done"), _S(2, "delentia_save_exchange_file", "dangling", idem)], unknown_ok)
    assert NEW in text
    assert text.index(OLD_FIRST) < text.index(NEW)                                   # right after the sentence it completes
    assert text.rstrip().endswith(OLD_LAST)                                           # the older sentences are all still there, in the same order
    assert (OLD_KEY in text) == bool(idem) and (not idem or text.index(NEW) < text.index(OLD_KEY))
    assert ("A person has said to go on." in text) == unknown_ok


def test_nothing_changes_when_the_unknown_step_only_reads_or_nothing_is_unknown():
    reads = note([_S(1, "delentia_read_repo_file", "dangling")])
    assert NEW not in reads and "OUTCOME UNKNOWN" in reads and OLD_FIRST not in reads
    done = note([_S(1, "delentia_save_exchange_file", "done")])
    assert NEW not in done and "OUTCOME UNKNOWN" not in done


def test_the_note_grants_no_permission():
    text = note([_S(2, "delentia_save_exchange_file", "dangling", "dl-abc")], unknown_ok=False)
    assert not re.search(r"\b(approved|allowed|you may|permission is granted|authori[sz]ed)\b", NEW, re.IGNORECASE)
    assert "same idempotency key" in text and "dl-abc" not in text              # the key itself is not put in front of the model

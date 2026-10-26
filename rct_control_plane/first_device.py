"""
Round 101C: the first approver without typing a key command.

A new device becomes an approver only after an existing approver signed for it. That leaves a first-run problem: on a fresh install nobody can approve anything, so the first device could not be added from the
web page. A page that simply creates the first approver would let ANY local program do it (the agent's own tools included), and that would end the rule that a person approves.

The answer is a one-time code that only the person at the keyboard sees:

  * `delentia approvals first-device-code` prints a code on the terminal (8 characters, no look-alike letters, valid 10 minutes, at most 5 wrong tries, used once). Only a hash is stored.
  * The Desk's Settings page asks for it while adding the first device. A right code makes THAT device an approver at once. After that, every further device needs an approver's signature as before.
  * It works only while nobody can approve: no approver key on the host and no active device. The moment one exists, the command refuses and a code that was issued stops working.
  * The command refuses to run for the agent: the sandbox marks every command it runs for the agent (DELENTIA_AGENT_SHELL) and refuses the command text itself. This is a speed bump of the same kind as the
    sandbox's other limits (the agent runs as the same OS user), not a wall; the code on the screen is what a person at the keyboard holds and a program that only reads the web page does not.

Standard library only.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from typing import Any, Dict, Optional

CODE_TTL_SECONDS = 600
MAX_ATTEMPTS = 5
CODE_LENGTH = 8
ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"            # 31 characters: no 0, 1, O, I, L (about 39.7 bits for 8 characters)
AGENT_SHELL_ENV = "DELENTIA_AGENT_SHELL"

SCHEMA = """
CREATE TABLE IF NOT EXISTS first_device_codes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    salt       TEXT NOT NULL,
    code_hash  TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    attempts   INTEGER NOT NULL DEFAULT 0,
    state      TEXT NOT NULL DEFAULT 'ACTIVE'
);
"""


class FirstDeviceError(ValueError):
    """A refusal with a reason a person can read. Never contains the code."""


def normalize(code: str) -> str:
    return "".join(ch for ch in str(code or "").upper() if ch.isalnum())


def _hash(salt: str, code: str) -> str:
    return hashlib.sha256(f"{salt}:{normalize(code)}".encode("utf-8")).hexdigest()


def display(code: str) -> str:
    return f"{code[:4]}-{code[4:]}"


def nobody_can_approve(persistence: Any) -> bool:
    """True while there is no approver key on the host and no active approval device."""
    from rct_control_plane.approvals import ApprovalError, trusted_approver_keys
    try:
        if trusted_approver_keys():
            return False
    except ApprovalError:
        return False                                            # an approvers file that exists but cannot be read is not "nobody": leave it to a person to look
    try:
        from rct_control_plane.passkeys import PasskeyStore
        return not PasskeyStore(persistence).active()
    except Exception:                                           # noqa: BLE001 - no table yet means no device
        return True


class FirstDeviceStore:
    def __init__(self, persistence: Any) -> None:
        self._persistence = persistence
        with persistence._connect() as conn:
            conn.executescript(SCHEMA)

    # ------------------------------------------------------------------ the person at the keyboard
    def issue(self, *, from_agent_shell: Optional[bool] = None) -> Dict[str, Any]:
        agent = bool(os.environ.get(AGENT_SHELL_ENV)) if from_agent_shell is None else from_agent_shell
        if agent:
            raise FirstDeviceError("this command is for the person at the keyboard; it will not run for the agent")
        if not nobody_can_approve(self._persistence):
            raise FirstDeviceError("someone can already approve here, so a first-device code is not needed. Add the next device in the Desk (Settings) and sign for it with an approver key")
        code = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))
        salt, now = secrets.token_hex(8), time.time()
        with self._persistence._connect() as conn:
            conn.execute("UPDATE first_device_codes SET state = 'REPLACED' WHERE state = 'ACTIVE'")
            conn.execute("INSERT INTO first_device_codes (salt, code_hash, created_at, expires_at) VALUES (?, ?, ?, ?)", (salt, _hash(salt, code), now, now + CODE_TTL_SECONDS))
        return {"code": code, "display": display(code), "expires_at": now + CODE_TTL_SECONDS, "ttl_seconds": CODE_TTL_SECONDS}

    # ------------------------------------------------------------------ the page
    def _active(self) -> Optional[tuple]:
        with self._persistence._connect() as conn:
            row = conn.execute("SELECT id, salt, code_hash, expires_at, attempts FROM first_device_codes WHERE state = 'ACTIVE' ORDER BY id DESC LIMIT 1").fetchone()
        if row is None:
            return None
        if float(row[3]) < time.time():
            with self._persistence._connect() as conn:
                conn.execute("UPDATE first_device_codes SET state = 'EXPIRED' WHERE id = ?", (row[0],))
            return None
        return row

    def status(self) -> Dict[str, Any]:
        """What the page may know without any secret: whether a code is waiting and until when."""
        row = self._active()
        open_now = nobody_can_approve(self._persistence)
        return {"open": open_now, "code_waiting": bool(row) and open_now, "expires_at": float(row[3]) if row and open_now else None}

    def check(self, code: str) -> int:
        """Returns the id of the live code if `code` is right and nobody can approve yet; raises otherwise. A try is RESERVED before the code is compared (one atomic update), so any number of
        guesses at the same moment can never get more than MAX_ATTEMPTS comparisons. A right code is not used up here: `consume(id)` does that, once."""
        if not nobody_can_approve(self._persistence):
            raise FirstDeviceError("someone can already approve here: a first device needs no code any more, and a new device needs an approver's signature")
        row = self._active()
        if row is None:
            raise FirstDeviceError("there is no live code: run `delentia approvals first-device-code` on this computer and use the code within 10 minutes")
        with self._persistence._connect() as conn:
            reserved = conn.execute("UPDATE first_device_codes SET attempts = attempts + 1 WHERE id = ? AND state = 'ACTIVE' AND attempts < ?", (row[0], MAX_ATTEMPTS)).rowcount == 1
            used = conn.execute("SELECT attempts FROM first_device_codes WHERE id = ?", (row[0],)).fetchone()
            # Only a WRONG guess that uses up the last try cancels the code. A request that could not get a try is just refused: cancelling the code for it would also cancel a request that already
            # holds a try and has the right code (found by CI on Python 3.10: with more than five requests at once, nobody got in).
            if reserved and used and int(used[0]) >= MAX_ATTEMPTS and not hmac.compare_digest(_hash(row[1], code), row[2]):
                conn.execute("UPDATE first_device_codes SET state = 'LOCKED' WHERE id = ? AND state = 'ACTIVE'", (row[0],))
        if not reserved:
            raise FirstDeviceError("there is no live code: the tries are used up; run `delentia approvals first-device-code` for a new one")
        if not hmac.compare_digest(_hash(row[1], code), row[2]):
            left = max(0, MAX_ATTEMPTS - int(used[0] if used else MAX_ATTEMPTS))
            raise FirstDeviceError("that code is not right" + (f" ({left} tries left)" if left else "; the code is cancelled, ask for a new one"))
        return int(row[0])

    def consume(self, code_id: Optional[int] = None) -> bool:
        """Use the code up. True for exactly one caller, however many ask at once."""
        with self._persistence._connect() as conn:
            if code_id is None:
                return conn.execute("UPDATE first_device_codes SET state = 'USED' WHERE state = 'ACTIVE'").rowcount >= 1
            return conn.execute("UPDATE first_device_codes SET state = 'USED' WHERE id = ? AND state = 'ACTIVE'", (code_id,)).rowcount == 1

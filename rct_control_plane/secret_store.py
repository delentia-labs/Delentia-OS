"""
Round 109: a key typed into the Desk is kept on this computer, so the person does not have to type it again after closing the program.

The owner's decision (2026-11-02): keep model keys permanently, as the agent runtimes this one follows do; when a key expires or is rotated is the person's own business. This module only decides HOW
it is kept, so that keeping it is not the same as leaving it lying about:

  * Windows: encrypted with DPAPI (CryptProtectData) for this Windows account, with a fixed extra secret. Another Windows account on the same computer, or a copy of the file on another computer,
    cannot read it. A program running as the SAME account can (that is what DPAPI means); the agent's shell is kept away from it by the places it may not read (secret_paths: the data folder is
    blocked), by the shell's environment that never carries a key, and by this being a file inside `<data folder>/keys`, which `delentia backup` leaves out even with --include-keys.
  * Everywhere else: a file readable by the owner only (mode 0600). Said plainly in `scheme()`: there the protection is the operating system's file permissions, nothing more.

What is stored is the value under its environment-variable NAME (the same names the credential pool and the providers read). At start the names that are not already set in the real environment are
loaded into this process's environment, never the other way round: an explicit environment variable always wins. Nothing here is ever returned to a page or logged: a caller can only learn which
names are saved, when, and the last four characters.

Off with DELENTIA_SECRET_STORE=off (a host that wants keys only in its environment).

Apache 2.0 - Delentia Labs
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

from rct_control_plane.data_home import data_home

OFF_ENV = "DELENTIA_SECRET_STORE"
FILE_NAME = "model_keys.dat"
_ENTROPY = b"delentia-model-keys-v1"
_MAGIC_DPAPI = b"DLTDPAPI1"
_MAGIC_PLAIN = b"DLTFILE01"
MAX_KEYS = 32


class SecretStoreError(RuntimeError):
    pass


def enabled() -> bool:
    return (os.getenv(OFF_ENV) or "").strip().lower() not in ("off", "0", "no", "false")


def store_path() -> Path:
    return (data_home() or (Path.home() / ".delentia")) / "keys" / FILE_NAME


def scheme() -> str:
    return "windows-dpapi" if sys.platform == "win32" else "file-0600"


def _dpapi(data: bytes, protect: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32, kernel32 = ctypes.WinDLL("crypt32", use_last_error=True), ctypes.WinDLL("kernel32", use_last_error=True)       # type: ignore[attr-defined]
    kernel32.LocalFree.argtypes, kernel32.LocalFree.restype = [ctypes.c_void_p], ctypes.c_void_p
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    buf, ent = ctypes.create_string_buffer(data, len(data)), ctypes.create_string_buffer(_ENTROPY, len(_ENTROPY))
    blob_in = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_ent = Blob(len(_ENTROPY), ctypes.cast(ent, ctypes.POINTER(ctypes.c_char)))
    blob_out = Blob()
    if not fn(ctypes.byref(blob_in), None, ctypes.byref(blob_ent), None, None, 0x1, ctypes.byref(blob_out)):          # 0x1: never show a window
        raise SecretStoreError(f"Windows could not {'protect' if protect else 'unprotect'} the saved keys (error {ctypes.get_last_error()})")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def _seal(payload: bytes) -> bytes:
    return _MAGIC_DPAPI + _dpapi(payload, True) if sys.platform == "win32" else _MAGIC_PLAIN + payload


def _unseal(blob: bytes) -> bytes:
    if blob.startswith(_MAGIC_DPAPI):
        if sys.platform != "win32":
            raise SecretStoreError("these saved keys were encrypted for a Windows account and cannot be read here")
        return _dpapi(blob[len(_MAGIC_DPAPI):], False)
    if blob.startswith(_MAGIC_PLAIN):
        return blob[len(_MAGIC_PLAIN):]
    raise SecretStoreError("the saved-keys file is not in a format this version knows")


def _read() -> Dict[str, Dict[str, Any]]:
    path = store_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(_unseal(path.read_bytes()).decode("utf-8"))
        keys = data.get("keys") if isinstance(data, dict) else None
        return {str(n): dict(v) for n, v in (keys or {}).items() if isinstance(v, dict) and isinstance(v.get("value"), str)}
    except (OSError, ValueError, SecretStoreError):
        return {}                                                         # unreadable (another account, damaged): the person is asked for the key again, nothing is guessed


def _write(keys: Dict[str, Dict[str, Any]]) -> None:
    path = store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = _seal(json.dumps({"v": 1, "keys": keys}, sort_keys=True).encode("utf-8"))
    fd, tmp = tempfile.mkstemp(prefix=".model_keys-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(blob)
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _check_name(name: str) -> str:
    from rct_control_plane.model_setup import SetupError, check_key_env_name
    try:
        return check_key_env_name(name)
    except SetupError as exc:
        raise SecretStoreError(str(exc)) from exc


def save(name: str, value: str) -> None:
    """Keep `value` under the environment-variable `name` on this computer."""
    if not enabled():
        raise SecretStoreError("keeping keys on this computer is switched off (DELENTIA_SECRET_STORE=off)")
    name = _check_name(name)
    if not value or len(value) > 4096 or any(c in value for c in "\r\n\x00"):
        raise SecretStoreError("the key is empty, too long, or contains a line break")
    keys = _read()
    if name not in keys and len(keys) >= MAX_KEYS:
        raise SecretStoreError(f"at most {MAX_KEYS} keys can be kept")
    keys[name] = {"value": value, "saved_at": time.time()}
    _write(keys)


def forget(name: str) -> bool:
    """Remove the saved key (and only the saved copy: the caller also clears this process's environment). True when there was one."""
    name = _check_name(name)
    keys = _read()
    if name not in keys:
        return False
    del keys[name]
    if keys:
        _write(keys)
    else:
        try:
            store_path().unlink()
        except OSError:
            pass
    return True


def status() -> List[Dict[str, Any]]:
    """Which names are saved, when, and the last four characters. Never the value."""
    return [{"env": n, "saved_at": v.get("saved_at"), "last4": v["value"][-4:] if len(v["value"]) >= 12 else ""} for n, v in sorted(_read().items())]


def status_view() -> Dict[str, Any]:
    """What a page may show: whether keeping is on, how it is protected, and the saved names with their age. Never a value."""
    return {"enabled": enabled(), "scheme": scheme(), "saved": status() if enabled() else []}


def apply_to_environment() -> List[str]:
    """Load saved keys into this process's environment, except names that are already set there. Returns the names loaded."""
    if not enabled():
        return []
    loaded: List[str] = []
    for name, entry in _read().items():
        if not os.environ.get(name):
            os.environ[name] = entry["value"]
            loaded.append(name)
    return loaded

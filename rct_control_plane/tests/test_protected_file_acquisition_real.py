"""Real filesystem races and fail-closed protected-file acceptance."""
import hashlib
import os

import pytest

from rct_control_plane.intent_contract import IntentContractError, _digest, build_plan, compare, validate_criteria
from rct_control_plane.verified_budget import supports_verified_reads

pytestmark = pytest.mark.skipif(not supports_verified_reads(), reason="POSIX no-follow required")


def test_observe_and_detect_changed_bytes(tmp_path):
    (tmp_path / 'a').write_bytes(b'original')
    plan = build_plan('keep file', validate_criteria([{'kind': 'file_unchanged', 'value': 'a'}]), tmp_path)
    assert plan['protected_sha256']['a'] == hashlib.sha256(b'original').hexdigest()
    assert compare(plan, '') == []
    (tmp_path / 'a').write_bytes(b'changed')
    assert compare(plan, '')


@pytest.mark.parametrize('name', ['../outside', '/etc/passwd', 'a/../b', './a', 'a//b', '.env', 'a\\b', 'a\x00b'])
def test_invalid_paths(tmp_path, name):
    with pytest.raises(IntentContractError):
        _digest(tmp_path, name)


@pytest.mark.parametrize('kind', ['leaf', 'directory', 'fifo', 'missing', 'oversize'])
def test_unsafe_sources(tmp_path, kind):
    target = tmp_path / 'source'
    target.write_bytes(b'content')
    if kind == 'leaf':
        (tmp_path / 'a').symlink_to(target)
        relative = 'a'
    elif kind == 'directory':
        (tmp_path / 'a').symlink_to(tmp_path, target_is_directory=True)
        relative = 'a/source'
    elif kind == 'fifo':
        os.mkfifo(tmp_path / 'a')
        relative = 'a'
    elif kind == 'oversize':
        with target.open('wb') as stream:
            stream.truncate(64 * 1024 * 1024 + 1)
        relative = 'source'
    else:
        relative = 'missing'
    with pytest.raises(IntentContractError):
        _digest(tmp_path, relative)


def test_directory_swap_before_open_cannot_follow_symlink(tmp_path, monkeypatch):
    folder = tmp_path / 'folder'
    folder.mkdir()
    (folder / 'a').write_bytes(b'original')
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'a').write_bytes(b'private')
    original_open = os.open

    def swap(path, flags, *args, **kwargs):
        if path == 'folder':
            folder.rename(tmp_path / 'old')
            folder.symlink_to(outside, target_is_directory=True)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, 'open', swap)
    with pytest.raises(IntentContractError):
        _digest(tmp_path, 'folder/a')


def test_opened_directory_remains_pinned_after_swap(tmp_path, monkeypatch):
    folder = tmp_path / 'folder'
    folder.mkdir()
    (folder / 'a').write_bytes(b'original')
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'a').write_bytes(b'private')
    original_open = os.open

    def swap(path, flags, *args, **kwargs):
        if path == 'a':
            folder.rename(tmp_path / 'old')
            folder.symlink_to(outside, target_is_directory=True)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, 'open', swap)
    assert _digest(tmp_path, 'folder/a') == hashlib.sha256(b'original').hexdigest()


def test_mutation_during_read_refused(tmp_path, monkeypatch):
    path = tmp_path / 'a'
    path.write_bytes(b'original')
    original_read = os.read
    changed = False

    def mutate(fd, size):
        nonlocal changed
        result = original_read(fd, size)
        if not changed:
            path.write_bytes(b'changed-length')
            changed = True
        return result

    monkeypatch.setattr(os, 'read', mutate)
    with pytest.raises(IntentContractError, match='changed during reading'):
        _digest(tmp_path, 'a')

"""Actual bounded filesystem reads; callback failure never publishes a bundle."""
import hashlib
import os

import pytest

from rct_control_plane.citation_acquisition import AcquisitionContext, acquire_citation_sources
from rct_control_plane.verified_budget import digest, supports_verified_reads

pytestmark = pytest.mark.skipif(not supports_verified_reads(), reason='requires POSIX descriptor-relative no-follow reads')


def setup(tmp_path, raw='ราคา 100 บาท\r\n'.encode()):
    (tmp_path/'report.txt').write_bytes(raw)
    context = AcquisitionContext.model_validate({'binding': {'actor': 'alice', 'workspace_root': str(tmp_path.resolve()),
        'policy_sha256': 'a'*64, 'catalog_sha256': 'b'*64}, 'contract_id': 'contract', 'version': 1, 'plan_sha256': 'c'*64})
    request = {'report': {'relative_path': 'report.txt', 'sha256': hashlib.sha256(raw).hexdigest()}}
    return context, request


def test_actual_bytes_and_receipt_bind_context_without_normalizing_text(tmp_path):
    context, request = setup(tmp_path)
    receipts = []
    bundle = acquire_citation_sources(tmp_path, request, {'report.txt'}, context, receipts.append)
    assert bundle.sources[0].text == 'ราคา 100 บาท\r\n'
    receipt = receipts[0]
    assert receipt['context'] == context.model_dump()
    assert receipt['source_bundle_sha256'] == digest(bundle.model_dump())
    assert receipt['receipt_sha256'] == digest({k:v for k,v in receipt.items() if k != 'receipt_sha256'})


@pytest.mark.parametrize('case', ['unauthorized', 'traversal', 'secret', 'duplicate', 'workspace', 'caller_text'])
def test_invalid_scope_rejected_before_any_read(tmp_path, monkeypatch, case):
    from rct_control_plane import citation_acquisition as module
    context, request = setup(tmp_path)
    allowed = {'report.txt'}
    if case == 'unauthorized': allowed = set()
    if case in ('traversal', 'secret'):
        path = '../report.txt' if case == 'traversal' else '.env'
        request['report']['relative_path'] = path
        allowed = {path}
    if case == 'duplicate': request['other'] = request['report'].copy()
    if case == 'workspace': context.binding.workspace_root = '/other'
    if case == 'caller_text': request['report']['text'] = 'invented'
    def forbidden(*args): pytest.fail('read occurred before scope checks')
    monkeypatch.setattr(module, 'current_bytes', forbidden)
    with pytest.raises(ValueError): acquire_citation_sources(tmp_path, request, allowed, context, lambda _: None)


@pytest.mark.parametrize('case', ['changed', 'invalid_utf8', 'oversize', 'symlink', 'fifo'])
def test_invalid_actual_source_produces_no_receipt(tmp_path, case):
    raw = b'\xff' if case == 'invalid_utf8' else b'x'*20001 if case == 'oversize' else b'original'
    context, request = setup(tmp_path, raw)
    path = tmp_path/'report.txt'
    if case == 'changed': path.write_bytes(b'changed')
    if case == 'symlink':
        path.unlink(); (tmp_path/'target.txt').write_bytes(raw); path.symlink_to('target.txt')
    if case == 'fifo': path.unlink(); os.mkfifo(path)
    receipts = []
    with pytest.raises((ValueError, OSError)):
        acquire_citation_sources(tmp_path, request, {'report.txt'}, context, receipts.append)
    assert receipts == []


def test_failed_receipt_persistence_does_not_return_sources(tmp_path):
    context, request = setup(tmp_path)
    def persist(_): raise OSError('disk full')
    with pytest.raises(OSError, match='disk full'):
        acquire_citation_sources(tmp_path, request, {'report.txt'}, context, persist)


def test_parent_symlink_is_refused(tmp_path):
    context, request = setup(tmp_path)
    (tmp_path/'actual').mkdir()
    (tmp_path/'actual'/'report.txt').write_bytes((tmp_path/'report.txt').read_bytes())
    (tmp_path/'alias').symlink_to('actual', target_is_directory=True)
    request['report']['relative_path'] = 'alias/report.txt'
    with pytest.raises(OSError):
        acquire_citation_sources(tmp_path, request, {'alias/report.txt'}, context, lambda _: pytest.fail('receipt issued'))


def test_later_source_failure_never_publishes_partial_batch(tmp_path):
    context, request = setup(tmp_path)
    (tmp_path/'second.txt').write_bytes(b'changed')
    request['second'] = {'relative_path': 'second.txt', 'sha256': '0'*64}
    receipts = []
    with pytest.raises(ValueError, match='changed'):
        acquire_citation_sources(tmp_path, request, {'report.txt', 'second.txt'}, context, receipts.append)
    assert not receipts

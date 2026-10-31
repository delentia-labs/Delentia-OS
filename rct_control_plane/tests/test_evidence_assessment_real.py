"""R1 boundaries: byte identity is separate from claimed facts and truth."""
from datetime import datetime, timedelta, timezone
import hashlib

import pytest
from pydantic import ValidationError

from rct_control_plane.evidence_assessment import SourceClaim, assess_evidence, observe

NOW = datetime(2026, 10, 31, tzinfo=timezone.utc)


def observation():
    return observe('read1', 'quote.json', 'ราคา 100 บาท'.encode('utf-8'), NOW)


def claim(**kw):
    return SourceClaim(**({'id': 'c1', 'observation_id': 'read1', 'subject': 'quote1',
                           'key': 'total_THB', 'value': '100', 'claimed_at': NOW} | kw))


def assess(claims, **kw):
    return assess_evidence([observation()], claims, now=NOW, max_age_seconds=60, **kw)


def test_observation_hashes_actual_thai_bytes_without_certifying_claim():
    o = observation()
    assert o.sha256 == hashlib.sha256('ราคา 100 บาท'.encode('utf-8')).hexdigest()
    result = assess([claim()])
    assert not result.needs_review and not result.claims[0].truth_verified
    assert result.scope == 'claimed_date_and_literal_disagreement'


@pytest.mark.parametrize('date,status', [(None, 'unknown'), (NOW, 'current'),
    (NOW - timedelta(seconds=60), 'current'), (NOW - timedelta(seconds=61), 'stale'),
    (NOW + timedelta(seconds=1), 'future')])
def test_claimed_freshness_boundaries(date, status):
    result = assess([claim(claimed_at=date)])
    assert result.claims[0].freshness == status
    assert result.needs_review == (status != 'current')


def test_same_observed_hash_does_not_remove_disagreement():
    result = assess([claim(), claim(id='c2', value='101')])
    assert result.needs_review
    assert result.claims[0].conflicting_claim_ids == ['c2']
    assert result.claims[1].conflicting_claim_ids == ['c1']


def test_distinct_subjects_and_equal_claims_are_not_conflicts():
    result = assess([claim(), claim(id='c2'), claim(id='c3', subject='quote2', value='101')])
    assert not result.needs_review
    assert all(not c.conflicting_claim_ids for c in result.claims)


@pytest.mark.parametrize('claims', [[claim(), claim()], [claim(observation_id='missing')]])
def test_invalid_claim_links_or_ids_fail_closed(claims):
    with pytest.raises(ValueError):
        assess(claims)


@pytest.mark.parametrize('age', [-1, True, float('nan'), 1.0, 315360001])
def test_malformed_age_policy_is_rejected(age):
    with pytest.raises(ValueError):
        assess_evidence([observation()], [claim()], now=NOW, max_age_seconds=age)


def test_naive_time_and_future_observation_are_rejected():
    with pytest.raises(ValidationError):
        claim(claimed_at=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError):
        assess_evidence([observation()], [claim()], now=NOW - timedelta(seconds=1), max_age_seconds=60)


def test_empty_inventory_needs_review_and_json_round_trip_preserves_scope():
    assert assess([]).needs_review
    from rct_control_plane.evidence_assessment import EvidenceAssessment
    result = assess([claim()])
    assert EvidenceAssessment.model_validate_json(result.model_dump_json()) == result

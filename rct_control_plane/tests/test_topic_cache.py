"""
Round 44 item I.3: real tests for topic_cache.py - the first, greenfield
multi-topic cache in this repo (confirmed via grep before writing it that
no prior cache implementation existed anywhere). Real SQLite persistence,
real SHA256 content hashing, real TTL expiry via wall-clock time - no
mocking.
"""
import time

import pytest

from rct_control_plane.topic_cache import TopicCache, topic_bucket


@pytest.fixture
def cache(tmp_path):
    return TopicCache(db_path=str(tmp_path / "topic_cache_test.db"))


class TestTopicBucket:
    def test_deterministic_across_calls(self):
        assert topic_bucket("explain the FDIA formula") == topic_bucket("explain the FDIA formula")

    def test_in_valid_range(self):
        b = topic_bucket("some real text", n_buckets=64)
        assert 0 <= b < 64

    def test_empty_text_is_bucket_zero_not_a_crash(self):
        assert topic_bucket("") == 0

    def test_respects_n_buckets_param(self):
        b = topic_bucket("a real topic string", n_buckets=8)
        assert 0 <= b < 8


class TestGetPut:
    def test_miss_on_empty_cache(self, cache):
        assert cache.get("fdia formula", "explain F=D^I*A") is None

    def test_put_then_get_real_round_trip(self, cache):
        cache.put("fdia formula", "explain F=D^I*A", {"answer": "real value"}, ttl_seconds=3600)
        hit = cache.get("fdia formula", "explain F=D^I*A")
        assert hit == {"answer": "real value"}

    def test_different_content_same_topic_is_a_real_miss(self, cache):
        cache.put("fdia formula", "explain F=D^I*A", {"answer": "A"}, ttl_seconds=3600)
        assert cache.get("fdia formula", "explain something else entirely") is None

    def test_exact_match_only_slightly_different_content_misses(self, cache):
        # Real proof this is exact-match, not fuzzy - see module docstring
        # for why fuzzy matching was deliberately left out of this MVP.
        cache.put("fdia formula", "explain the FDIA formula please", {"a": 1}, ttl_seconds=3600)
        assert cache.get("fdia formula", "explain the FDIA formula, please") is None

    def test_put_overwrites_existing_entry_for_same_key(self, cache):
        cache.put("topic", "content", {"v": 1}, ttl_seconds=3600)
        cache.put("topic", "content", {"v": 2}, ttl_seconds=3600)
        assert cache.get("topic", "content") == {"v": 2}
        assert cache.count() == 1  # real overwrite, not a duplicate row

    def test_expired_entry_is_a_real_miss(self, cache):
        cache.put("topic", "content", {"v": 1}, ttl_seconds=-1)  # already expired
        assert cache.get("topic", "content") is None

    def test_expired_entry_is_still_counted_until_a_real_cleanup_runs(self, cache):
        cache.put("topic", "content", {"v": 1}, ttl_seconds=-1)
        assert cache.count(include_expired=True) == 1
        assert cache.count(include_expired=False) == 0

    def test_persists_across_separate_instances_same_db_path(self, tmp_path):
        db_path = str(tmp_path / "shared.db")
        TopicCache(db_path=db_path).put("t", "c", {"real": True}, ttl_seconds=3600)
        second = TopicCache(db_path=db_path)
        assert second.get("t", "c") == {"real": True}

    def test_leading_trailing_whitespace_is_normalized(self, cache):
        cache.put("topic", "  content with spaces  ", {"v": 1}, ttl_seconds=3600)
        assert cache.get("topic", "content with spaces") == {"v": 1}


class TestRealTTLBehavior:
    def test_entry_expires_for_real_after_ttl_elapses(self, cache):
        cache.put("topic", "content", {"v": 1}, ttl_seconds=0.2)
        assert cache.get("topic", "content") == {"v": 1}
        time.sleep(0.3)
        assert cache.get("topic", "content") is None

"""
Round 50 (PR #87 CI failure): SemanticAnalyzer loads NLTK data lazily. The
first use of stop_words fetches stopwords/punkt/punkt_tab; extract_topics must
therefore read stop_words before calling word_tokenize, or a fresh machine
(CI) raises LookupError('punkt_tab'). Real NLTK; only the data loader is
observed.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import nltk.tokenize

import rct_control_plane.algo_34_swcar as swcar


def test_extract_topics_ensures_nltk_data_before_tokenizing(monkeypatch):
    order = []
    real_loader = swcar._load_nltk_stopwords
    real_tokenize = nltk.tokenize.word_tokenize

    def loader():
        order.append("data")
        return real_loader()

    def tokenize(text, *args, **kwargs):
        order.append("tokenize")
        return real_tokenize(text, *args, **kwargs)

    monkeypatch.setattr(swcar, "_load_nltk_stopwords", loader)
    monkeypatch.setattr(nltk.tokenize, "word_tokenize", tokenize)
    analyzer = swcar.SemanticAnalyzer()
    topics = analyzer.extract_topics("Governance keeps autonomous agents accountable. Governance matters.")
    assert order[:2] == ["data", "tokenize"]
    assert any(t.keyword == "governance" and t.frequency == 2 for t in topics)


def test_constructor_stays_cheap():
    """The point of #87: building the analyzer loads neither NLTK data nor spaCy."""
    analyzer = swcar.SemanticAnalyzer()
    assert analyzer._stop_words is None

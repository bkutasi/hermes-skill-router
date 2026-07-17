"""Tests for core behavioral contracts of the 5-layer skill retriever.

These tests defend real contracts: hard trigger matching semantics, RRF
fusion math, confidence gating, description extraction, and the singleton
pattern. External dependencies (jieba, numpy, requests, hermes_constants)
are mocked — no installation required.
"""

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Path setup ──────────────────────────────────────────────
SRC_DIR = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

# ── Mock external dependencies before import ──────────────
# jieba
_jieba = types.ModuleType("jieba")
_jieba.cut = lambda text: text.split()
_jieba.initialize = lambda: None
sys.modules.setdefault("jieba", _jieba)

# numpy
_np = types.ModuleType("numpy")
_np.array = MagicMock()
_np.dot = MagicMock(return_value=[])
_np.linalg = MagicMock()
_np.linalg.norm = MagicMock(return_value=1.0)
_np.argsort = MagicMock(return_value=[])
_np.isscalar = lambda x: not hasattr(x, "__iter__")
_np.float32 = MagicMock
sys.modules.setdefault("numpy", _np)

# requests
_requests = types.ModuleType("requests")
_requests.post = MagicMock()
sys.modules.setdefault("requests", _requests)

# yaml
_yaml = types.ModuleType("yaml")
_yaml.safe_load = MagicMock(return_value={})
sys.modules.setdefault("yaml", _yaml)

# hermes_constants
_hermes_const = types.ModuleType("hermes_constants")
_hermes_const.get_hermes_home = lambda: Path.home() / ".hermes"
sys.modules.setdefault("hermes_constants", _hermes_const)

# ── Import after mocks are in place ──────────────────────
from skill_retriever import (
    SkillRetriever,
    _is_subsequence,
    _HARD_TRIGGERS,
    _RRF_W_FTS5,
    _RRF_W_SYN,
    _RRF_W_EMB,
    _RRF_K,
    _CONFIDENCE_THRESHOLD,
    _MIN_RRF_SCORE,
)


# ── _is_subsequence tests ─────────────────────────────────


class TestIsSubsequence:
    def test_basic_match(self):
        """Chars appearing in order within text, close together."""
        assert _is_subsequence(['d', 'e', 'b', 'u', 'g'], 'please debug this') is True

    def test_gap_exceeded(self):
        """Gap of 4 between 能 and 指 exceeds max_gap=3."""
        assert _is_subsequence(['技', '能', '指', '南'], '梳理一下现有的技能，弄个说明指南') is False

    def test_not_found(self):
        """Chars not present in text."""
        assert _is_subsequence(['x', 'y', 'z'], 'abc') is False

    def test_single_char(self):
        """Single char always finds itself."""
        assert _is_subsequence(['a'], 'abc') is True

    def test_empty_chars(self):
        """Empty char list — vacuously true."""
        assert _is_subsequence([], 'anything') is True

    def test_order_matters(self):
        """Chars out of order return False."""
        assert _is_subsequence(['b', 'a'], 'ab') is False


# ── Hard trigger tests ────────────────────────────────────


class TestHardTrigger:
    def test_empty_query(self):
        """Empty query returns None."""
        assert SkillRetriever._hard_trigger("") is None

    def test_no_match(self, monkeypatch):
        """Query with no matching triggers returns None."""
        monkeypatch.setattr("skill_retriever._HARD_TRIGGERS", [("debug", "debugging-skill")])
        assert SkillRetriever._hard_trigger("what is the weather") is None

    def test_exact_match(self, monkeypatch):
        """Exact substring match returns the skill."""
        monkeypatch.setattr("skill_retriever._HARD_TRIGGERS", [("debug", "debugging-skill")])
        assert SkillRetriever._hard_trigger("please debug this") == "debugging-skill"

    def test_short_ascii_word_boundary(self, monkeypatch):
        """Short ASCII triggers require word boundaries (debug ⊄ debugging)."""
        monkeypatch.setattr("skill_retriever._HARD_TRIGGERS", [("debug", "debugging-skill")])
        assert SkillRetriever._hard_trigger("please debugging this") is None
        assert SkillRetriever._hard_trigger("please debug this") == "debugging-skill"

    def test_long_or_multiword_still_substring(self, monkeypatch):
        """Multi-word / long triggers still use plain substring matching."""
        monkeypatch.setattr("skill_retriever._HARD_TRIGGERS", [
            ("root cause", "debugging-skill"),
            ("systematic-debugging", "debugging-skill"),
        ])
        assert SkillRetriever._hard_trigger("find the root cause now") == "debugging-skill"
        assert SkillRetriever._hard_trigger("use systematic-debugging please") == "debugging-skill"

    def test_longest_wins(self, monkeypatch):
        """When two triggers match, the longer (more specific) one wins."""
        monkeypatch.setattr("skill_retriever._HARD_TRIGGERS", [
            ("debug", "debugging-skill"),
            ("debug python", "python-debug-skill"),
        ])
        assert SkillRetriever._hard_trigger("debug python") == "python-debug-skill"

    def test_tiebreak_by_position(self, monkeypatch):
        """Equal-length triggers: earliest position in query wins."""
        monkeypatch.setattr("skill_retriever._HARD_TRIGGERS", [
            ("python", "python-skill-a"),
            ("python", "python-skill-b"),
        ])
        # Both same length, first in list is returned (stable sort by position)
        result = SkillRetriever._hard_trigger("I love python")
        assert result in ("python-skill-a", "python-skill-b")

    def test_whitespace_only(self):
        """Whitespace-only query returns None."""
        assert SkillRetriever._hard_trigger("   ") is None

    def test_cjk_exact_match(self, monkeypatch):
        """CJK trigger matches via exact substring."""
        monkeypatch.setattr("skill_retriever._HARD_TRIGGERS", [("调试", "debugging-skill")])
        assert SkillRetriever._hard_trigger("帮我调试一下") == "debugging-skill"

    def test_mixed_cjk_ascii_no_fuzzy(self, monkeypatch):
        """Mixed CJK/ASCII triggers only match via exact substring, not fuzzy."""
        monkeypatch.setattr("skill_retriever._HARD_TRIGGERS", [("Python数据", "data-skill")])
        # Should NOT fuzzy-match "Python的据" (subsequence of CJK chars)
        assert SkillRetriever._hard_trigger("Python的据") is None
        # But SHOULD exact-match
        assert SkillRetriever._hard_trigger("用Python数据处理") == "data-skill"


# ── RRF fusion tests ──────────────────────────────────────


class TestRRFFusion:
    def test_empty_all(self):
        """Empty inputs produce empty output."""
        assert SkillRetriever._rrf_fusion([], [], []) == []

    def test_single_layer_single_item(self):
        """One item in one layer appears in output."""
        result = SkillRetriever._rrf_fusion([(0, 1.0)], [], [])
        assert len(result) == 1
        assert result[0][0] == 0  # idx 0

    def test_combines_rankings(self):
        """Items from different layers both appear in output."""
        result = SkillRetriever._rrf_fusion([(0, 1.0)], [(1, 0.9)], [])
        idxs = [idx for idx, _ in result]
        assert 0 in idxs
        assert 1 in idxs

    def test_fts5_weight_highest(self):
        """FTS5 rank-1 score > Synonym rank-1 score > Embedding rank-1 score."""
        fts5 = SkillRetriever._rrf_fusion([(0, 1.0)], [], [])
        syn = SkillRetriever._rrf_fusion([], [(0, 1.0)], [])
        emb = SkillRetriever._rrf_fusion([], [], [(0, 1.0)])
        fts5_score = fts5[0][1]
        syn_score = syn[0][1]
        emb_score = emb[0][1]
        assert fts5_score > syn_score > emb_score

    def test_weight_ratios(self):
        """Verify exact weight ratios: 0.45 / 0.35 / 0.20."""
        fts5 = SkillRetriever._rrf_fusion([(0, 1.0)], [], [])
        syn = SkillRetriever._rrf_fusion([], [(0, 1.0)], [])
        emb = SkillRetriever._rrf_fusion([], [], [(0, 1.0)])
        fts5_score = fts5[0][1]
        syn_score = syn[0][1]
        emb_score = emb[0][1]
        # All rank 1, so score = weight / (k + 1)
        assert abs(fts5_score - _RRF_W_FTS5 / (_RRF_K + 1)) < 1e-9
        assert abs(syn_score - _RRF_W_SYN / (_RRF_K + 1)) < 1e-9
        assert abs(emb_score - _RRF_W_EMB / (_RRF_K + 1)) < 1e-9

    def test_same_item_in_all_layers_gets_highest_score(self):
        """Item appearing as rank-1 in all layers gets the sum of all weights."""
        result = SkillRetriever._rrf_fusion([(0, 1.0)], [(0, 0.9)], [(0, 0.8)])
        expected = (_RRF_W_FTS5 + _RRF_W_SYN + _RRF_W_EMB) / (_RRF_K + 1)
        assert abs(result[0][1] - expected) < 1e-9

    def test_sorted_descending(self):
        """Output is sorted by score descending."""
        # idx 0 is rank 1 in fts5 (highest weight layer)
        # idx 1 is rank 1 in emb (lowest weight layer)
        result = SkillRetriever._rrf_fusion([(0, 1.0)], [], [(1, 0.9)])
        scores = [s for _, s in result]
        assert scores == sorted(scores, reverse=True)


# ── Confidence gate tests ─────────────────────────────────


class TestConfidenceGate:
    def test_threshold_is_positive(self):
        """Confidence threshold is a positive number."""
        assert _CONFIDENCE_THRESHOLD > 0

    def test_min_rrf_score_is_positive(self):
        """Min RRF score is a positive number, lower than confidence threshold."""
        assert _MIN_RRF_SCORE > 0
        assert _MIN_RRF_SCORE < _CONFIDENCE_THRESHOLD


# ── _extract_description tests ─────────────────────────────


class TestExtractDescription:
    def test_basic_frontmatter(self):
        """Standard frontmatter with description field."""
        content = "---\ndescription: Test skill\n---\n# Body"
        assert SkillRetriever._extract_description(content) == "Test skill"

    def test_no_frontmatter(self):
        """No frontmatter returns empty string."""
        assert SkillRetriever._extract_description("# No frontmatter") == ""

    def test_quoted_description(self):
        """Quoted description value is unquoted."""
        content = '---\ndescription: "Quoted desc"\n---\n'
        assert SkillRetriever._extract_description(content) == "Quoted desc"

    def test_single_quoted(self):
        """Single-quoted description is unquoted."""
        content = "---\ndescription: 'Single quoted'\n---\n"
        assert SkillRetriever._extract_description(content) == "Single quoted"

    def test_no_description_field(self):
        """Frontmatter without description field returns empty."""
        content = "---\nname: some-skill\n---\n"
        assert SkillRetriever._extract_description(content) == ""

    def test_incomplete_frontmatter(self):
        """Only one --- delimiter returns empty."""
        content = "---\ndescription: test\n"
        assert SkillRetriever._extract_description(content) == ""


# ── Singleton pattern tests ────────────────────────────────


class TestSingleton:
    def test_get_skill_retriever_returns_same_instance(self):
        """get_skill_retriever() returns the same singleton across calls."""
        # Reset singleton for test isolation
        import skill_retriever
        original = skill_retriever._SINGLETON
        skill_retriever._SINGLETON = None
        try:
            r1 = skill_retriever.get_skill_retriever()
            r2 = skill_retriever.get_skill_retriever()
            assert r1 is r2
        finally:
            skill_retriever._SINGLETON = original

    def test_singleton_is_skill_retriever(self):
        """The singleton is a SkillRetriever instance."""
        import skill_retriever
        original = skill_retriever._SINGLETON
        skill_retriever._SINGLETON = None
        try:
            r = skill_retriever.get_skill_retriever()
            assert isinstance(r, SkillRetriever)
        finally:
            skill_retriever._SINGLETON = original


# ── retrieve_detailed empty query tests ──────────────────


class TestRetrieveDetailed:
    def test_empty_query_returns_none_layer(self):
        """Empty query returns empty skills and 'none' layer."""
        r = SkillRetriever()
        result = r.retrieve_detailed("")
        assert result["skills"] == []
        assert result["layer"] == "none"

    def test_whitespace_query_returns_none_layer(self):
        """Whitespace-only query returns empty."""
        r = SkillRetriever()
        result = r.retrieve_detailed("   ")
        assert result["skills"] == []
        assert result["layer"] == "none"


# ── Embedding health state tests ──────────────────────────


class TestEmbeddingHealth:
    def test_emb_not_ready_on_fresh_instance(self):
        """_emb_ready is False on a fresh SkillRetriever instance."""
        r = SkillRetriever()
        assert r._emb_ready is False

    def test_is_embedding_ready_false_when_matrix_none(self):
        """is_embedding_ready() returns False when _emb_matrix is None."""
        r = SkillRetriever()
        r._emb_matrix = None
        assert r.is_embedding_ready() is False

    def test_is_embedding_ready_true_after_success(self):
        """is_embedding_ready() returns True when _emb_ready and _emb_matrix set."""
        r = SkillRetriever()
        r._emb_ready = True
        r._emb_matrix = MagicMock()  # non-None
        assert r.is_embedding_ready() is True

    def test_emb_error_none_on_fresh_instance(self):
        """_emb_error is None on a fresh instance."""
        r = SkillRetriever()
        assert r._emb_error is None


# ── Query embedding cache tests ───────────────────────────


class TestQueryEmbeddingCache:
    def test_cache_returns_same_result(self):
        """Calling _embed_query twice with same query hits HTTP only once."""
        r = SkillRetriever()
        r._emb_matrix = MagicMock()  # non-None so we proceed
        r._emb_base_url = "http://fake:8080/v1"
        r._emb_api_key = ""
        r._emb_model_name = "test-model"
        r._query_emb_cache.clear()

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": [{"index": 0, "embedding": [0.1, 0.2, 0.3]}]}
        mock_resp.raise_for_status = MagicMock()

        with patch("requests.post", return_value=mock_resp) as mock_post:
            result1 = r._embed_query("test query")
            result2 = r._embed_query("test query")

        assert mock_post.call_count == 1
        assert result1 is result2  # same cached object

    def test_cache_different_queries(self):
        """Two different queries trigger two HTTP calls."""
        r = SkillRetriever()
        r._emb_matrix = MagicMock()
        r._emb_base_url = "http://fake:8080/v1"
        r._emb_api_key = ""
        r._emb_model_name = "test-model"
        r._query_emb_cache.clear()

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": [{"index": 0, "embedding": [0.1, 0.2, 0.3]}]}
        mock_resp.raise_for_status = MagicMock()

        with patch("requests.post", return_value=mock_resp) as mock_post:
            r._embed_query("query one")
            r._embed_query("query two")

        assert mock_post.call_count == 2

    def test_cache_eviction_at_max(self):
        """Cache evicts oldest entries beyond max size."""
        r = SkillRetriever()
        r._emb_matrix = MagicMock()
        r._emb_base_url = "http://fake:8080/v1"
        r._emb_api_key = ""
        r._emb_model_name = "test-model"
        r._query_emb_cache.clear()
        r._query_emb_cache_max = 2  # small for testing

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": [{"index": 0, "embedding": [0.1, 0.2, 0.3]}]}
        mock_resp.raise_for_status = MagicMock()

        with patch("requests.post", return_value=mock_resp):
            r._embed_query("q1")
            r._embed_query("q2")
            r._embed_query("q3")  # should evict "q1"

        assert "q1" not in r._query_emb_cache
        assert "q2" in r._query_emb_cache
        assert "q3" in r._query_emb_cache


# ── Non-blocking first query tests ────────────────────────


class TestNonBlockingFirstQuery:
    def test_returns_empty_when_loading(self):
        """When _loading=True and _ready=False, returns empty without calling _lazy_init."""
        r = SkillRetriever()
        r._ready = False
        r._loading = True

        with patch.object(r, "_lazy_init") as mock_init:
            result = r.retrieve_detailed("test query")

        assert result == {"skills": [], "layer": "none"}
        mock_init.assert_not_called()

    def test_retries_init_on_first_call_when_not_loading(self):
        """When _ready=False and _loading=False and never attempted, retries init."""
        r = SkillRetriever()
        r._ready = False
        r._loading = False
        r._last_init_attempt = 0.0  # never attempted → should retry

        with patch.object(r, "_lazy_init") as mock_init:
            # _lazy_init mock won't set _ready, so we still return empty
            result = r.retrieve_detailed("test query")

        mock_init.assert_called_once()
        assert result == {"skills": [], "layer": "none"}

    def test_backoff_skips_init_within_window(self):
        """When last attempt was <30s ago and still not ready, skips retry."""
        r = SkillRetriever()
        r._ready = False
        r._loading = False
        import time as _time
        r._last_init_attempt = _time.monotonic()  # just now

        with patch.object(r, "_lazy_init") as mock_init:
            result = r.retrieve_detailed("test query")

        mock_init.assert_not_called()
        assert result == {"skills": [], "layer": "none"}


# ── Skill directory scan tests ───────────────────────────


class TestScanSkillDir:
    def test_skips_hidden_dirs(self, tmp_path, monkeypatch):
        """Dotdirs like .archive are not indexed."""
        monkeypatch.setenv("HERMES_DISABLE_SKILL_RETRIEVAL", "1")

        skills = tmp_path / "skills"
        (skills / "live-skill").mkdir(parents=True)
        (skills / "live-skill" / "SKILL.md").write_text(
            "---\ndescription: live\n---\n", encoding="utf-8"
        )
        (skills / ".archive" / "dead-skill").mkdir(parents=True)
        (skills / ".archive" / "dead-skill" / "SKILL.md").write_text(
            "---\ndescription: dead\n---\n", encoding="utf-8"
        )
        (skills / ".hub" / "hub-skill").mkdir(parents=True)
        (skills / ".hub" / "hub-skill" / "SKILL.md").write_text(
            "---\ndescription: hub\n---\n", encoding="utf-8"
        )

        r = SkillRetriever()
        r._skill_names = []
        r._skill_descs = []
        r._skill_paths = {}
        r._scan_skill_dir(skills, set())
        assert r._skill_names == ["live-skill"]
        assert "dead-skill" not in r._skill_names
        assert "hub-skill" not in r._skill_names


class TestTriggerFilter:
    def test_drops_triggers_for_missing_skills(self, monkeypatch):
        """L1 table is filtered to skills present after scan."""
        import skill_retriever as sr_mod
        from skill_retriever import SkillRetriever

        monkeypatch.setenv("HERMES_DISABLE_SKILL_RETRIEVAL", "1")
        monkeypatch.setattr(
            sr_mod,
            "_HARD_TRIGGERS",
            [("live", "live-skill"), ("ghost", "missing-skill")],
        )
        r = SkillRetriever()
        r._skill_names = ["live-skill"]
        r._skill_descs = ["live"]
        r._skill_paths = {"live-skill": Path("/tmp/x")}
        # Simulate the filter block from _lazy_init
        valid = set(r._skill_names)
        sr_mod._HARD_TRIGGERS = [
            (t, s) for t, s in sr_mod._HARD_TRIGGERS if s in valid
        ]
        assert sr_mod._HARD_TRIGGERS == [("live", "live-skill")]


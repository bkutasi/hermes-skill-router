"""Skill retrieval: 5-layer architecture.


Layer 1: Hard triggers — exact keyword → direct return (100% deterministic)
Layer 2: FTS5 BM25 — clean text search (name + description only)
Layer 3: Synonym dictionary — independent bonus scoring layer
Layer 4: Dense Embedding — sentence-transformers cosine similarity
Layer 5: RRF fusion — combine layers 2-4, return top-k

Usage:
    retriever = get_skill_retriever()
    if retriever.is_ready():
        hints = retriever.retrieve("help me debug this", top_k=5)
"""

import importlib.util
import logging
import math
import os
import re
import threading
import time
from collections import Counter, OrderedDict, defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

logger = logging.getLogger(__name__)

_DISABLE_ENV = "HERMES_DISABLE_SKILL_RETRIEVAL"
_TOP_K_ENV = "HERMES_SKILL_RETRIEVAL_TOP_K"

# RRF parameters
_RRF_K = 60
_RRF_W_FTS5 = 0.45      # FTS5 text matching
_RRF_W_SYN = 0.35       # Synonym dictionary
_RRF_W_EMB = 0.20       # Dense embedding
# Minimum RRF score to include (filters noise)
_MIN_RRF_SCORE = 0.003
# Confidence threshold: top-1 must score above this to be returned.
# Below this, the query likely doesn't match any skill well.
_CONFIDENCE_THRESHOLD = 0.015  # Empirically determined — filters noise effectively

# Module-level compiled regex patterns for hard trigger matching
_CJK_RE = re.compile('[\u4e00-\u9fff]')
_ASCII_RE = re.compile(r'[a-zA-Z]')

_SINGLETON: "SkillRetriever | None" = None
_SINGLETON_LOCK = threading.Lock()

# Maps exact substring → skill name.
# These bypass all ranking — if query contains the trigger, return directly.
#
# Triggers are auto-generated from your skill library by:
#   python scripts/build_real_config.py
# Edit src/hard_triggers_generated.py and re-run if skills change.
_HARD_TRIGGERS: list[tuple[str, str]] = [
    # ── Auto-generated (from build_real_config.py) ──
]

# Load generated triggers at import time using importlib (not exec)
_triggers_file = Path(__file__).parent / "hard_triggers_generated.py"
if _triggers_file.exists():
    try:
        _spec = importlib.util.spec_from_file_location(
            "hard_triggers_generated", _triggers_file
        )
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _generated = getattr(_mod, "_HARD_TRIGGERS", [])
        if _generated:
            _HARD_TRIGGERS = _generated
            logger.info(
                "Loaded %d hard triggers from %s",
                len(_HARD_TRIGGERS), _triggers_file.name,
            )
    except Exception as _e:
        logger.warning("Failed to load generated triggers: %s", _e)


def _is_subsequence(chars: list[str], text: str, max_gap: int = 3) -> bool:
    """Check if all chars appear in order within text, with max gap between consecutive matches.

    >>> _is_subsequence(['d', 'e', 'b', 'u', 'g'], 'please debug this')
    True
    >>> _is_subsequence(['d', 'b', 'g'], 'debug')
    False  # 'b' appears before 'd' in subsequence order
    >>> _is_subsequence(['技', '能', '指', '南'], '梳理一下现有的技能，弄个说明指南')
    False  # gap of 4 between 能 and 指 exceeds max_gap=3
    """
    pos = -1  # position of last match
    for c in chars:
        idx = text.find(c, pos + 1)
        if idx == -1:
            return False
        if pos >= 0 and idx - pos - 1 > max_gap:
            return False
        pos = idx
    return True


def get_skill_retriever() -> "SkillRetriever":
    """Return the global singleton, creating it on first call."""
    global _SINGLETON
    if _SINGLETON is None:
        with _SINGLETON_LOCK:
            if _SINGLETON is None:
                _SINGLETON = SkillRetriever()
    return _SINGLETON


class SkillRetriever:
    """5-layer skill retrieval: Hard Trigger → FTS5 → Synonym → Embedding → RRF."""

    def __init__(self) -> None:
        self._ready = False
        self._loading = False
        self._error: str | None = None
        self._skill_names: list[str] = []
        self._skill_descs: list[str] = []
        self._doc_tokens: list[list[str]] = []
        self._idf: dict[str, float] = {}
        # Synonym structures
        self._synonyms: dict[str, list[str]] = {}       # skill → [syn, ...]
        self._synonym_index: dict[str, list[tuple[str, float]]] = {}  # token → [(skill, weight)]
        self._skill_paths: dict[str, Path] = {}          # skill_name → SKILL.md path
        self._skill_name_to_idx: dict[str, int] = {}      # skill_name → list index (O(1) lookup)
        # Embedding (HTTP-based, no local model)
        self._emb_matrix = None
        self._emb_ready = False          # embedding endpoint confirmed working
        self._emb_error: str | None = None  # last embedding error, None if healthy
        self._query_emb_cache: "OrderedDict[str, object]" = OrderedDict()
        self._query_emb_cache_max = 256
        self._last_init_attempt = 0.0  # monotonic timestamp of last _lazy_init call
        self._emb_base_url = ""
        self._emb_api_key = ""
        self._emb_model_name = "default"
        self._jieba_initialized = False
        self._top_k = int(os.environ.get(_TOP_K_ENV, "5"))

        # Check disable BEFORE spawning the background thread
        if os.environ.get(_DISABLE_ENV, "").lower() in ("1", "true", "yes"):
            logger.info("Skill retrieval disabled via %s", _DISABLE_ENV)
            return

        # Start background initialization only if not disabled
        threading.Thread(target=self._lazy_init, daemon=True).start()

    def is_ready(self) -> bool:
        return self._ready

    def is_loading(self) -> bool:
        return self._loading
    def is_embedding_ready(self) -> bool:
        """True only if L4 embedding is operational."""
        return self._emb_ready

    def error(self) -> str | None:
        return self._error

    def retrieve(self, query: str, top_k: int | None = None) -> list[str]:
        """Return top-k skill names matching the query.

        For detailed match info (including layer and content), use
        ``retrieve_detailed()`` instead.
        """
        result = self.retrieve_detailed(query, top_k)
        return result["skills"]

    def retrieve_detailed(self, query: str, top_k: int | None = None) -> dict:
        """Return detailed match info: skills, layer, and content.

        Returns:
            {
                "skills": ["skill-name", ...],
                "layer": "L1" | "L2-5" | "none",
                "skill_name": "skill-name"  # only for L1
            }
        """
        if not query or not query.strip():
            return {"skills": [], "layer": "none"}

        # Disabled check — must be before L1 to prevent any processing
        if os.environ.get(_DISABLE_ENV, "").lower() in ("1", "true", "yes"):
            return {"skills": [], "layer": "none"}

        # ── Layer 1: Hard triggers (instant return, no ranking) ──
        hard_hit = self._hard_trigger(query)
        if hard_hit:
            logger.info("Skill retriever L1 hard trigger → %s", hard_hit)
            return {"skills": [hard_hit], "layer": "L1", "skill_name": hard_hit}

        # ── Layers 2-5: Full retrieval pipeline ──
        if not self._ready:
            if self._loading:
                logger.debug("Skill retriever still loading, skipping query")
                return {"skills": [], "layer": "none"}
            # Not loading and not ready — init failed or hasn't started.
            # Retry with backoff: only if ≥30s since the last attempt.
            # First call (last_attempt == 0) always retries.
            now = time.monotonic()
            if now - self._last_init_attempt < 30.0:
                logger.debug(
                    "Skill retriever not ready, backing off (%.1fs since last attempt)",
                    now - self._last_init_attempt,
                )
                return {"skills": [], "layer": "none"}
            logger.info("Skill retriever: retrying init (not ready)")
            self._lazy_init()
            if not self._ready:
                logger.warning("Skill retriever not ready after init attempt")
                return {"skills": [], "layer": "none"}

        k = top_k or self._top_k
        try:
            result = self._retrieve_inner(query, k)
            if result:
                layer_count = 3 if self._emb_ready else 2
                logger.info(
                    "Skill retriever L2-5: %d skills (%d/3 layers) for [%s]",
                    len(result), layer_count, query[:50],
                )
            return {"skills": result, "layer": "L2-5" if result else "none"}
        except Exception as e:
            logger.warning("Skill retrieval failed: %s", e)
            return {"skills": [], "layer": "none"}

    def get_skill_content(self, skill_name: str) -> str | None:
        """Read and return the full SKILL.md content for a skill."""
        path = self._skill_paths.get(skill_name)
        if path and path.exists():
            try:
                return path.read_text(encoding="utf-8")
            except Exception:
                pass
        logger.warning("Skill content not found for %s (not in cache)", skill_name)
        return None

    def get_skill_desc(self, skill_name: str) -> str:
        """Return the description for a skill, or empty string if unknown."""
        idx = self._skill_name_to_idx.get(skill_name)
        if idx is not None and idx < len(self._skill_descs):
            return self._skill_descs[idx]
        return ""

    @staticmethod
    def _hard_trigger(query: str) -> str | None:
        """Layer 1: 3-tier matching against hard trigger table.

        Tier 1: Exact substring match (fastest, 100% precise)
                 Collects ALL matches, picks longest trigger (most specific),
                 then earliest position in query (closest to intent).
        Tier 2: Subsequence match — trigger CJK chars appear in order in query
                 with max 3-char gap between consecutive matched chars.
        Tier 3: Regex fuzzy — trigger segments with optional gaps (0-3 chars)

        All tiers collect ALL matches and pick the longest trigger.
        """
        q = query.strip()
        if not q:
            return None

        # Tier 1: Collect ALL exact substring matches, pick the best one
        tier1_matches: list[tuple[str, str, int]] = []  # (trigger, skill, position)
        for trigger, skill in _HARD_TRIGGERS:
            idx = q.find(trigger)
            if idx != -1:
                tier1_matches.append((trigger, skill, idx))

        if tier1_matches:
            # Longest trigger wins (most specific), ties broken by earliest position
            tier1_matches.sort(key=lambda x: (-len(x[0]), x[2]))
            return tier1_matches[0][1]

        # Tier 2+3: Only for triggers with 2+ CJK characters
        #           and NO ASCII letters (ASCII-containing triggers like
        #           "Python数据" are too ambiguous for fuzzy matching)
        fuzzy_matches: list[tuple[str, str]] = []  # (trigger, skill)
        for trigger, skill in _HARD_TRIGGERS:
            cjk_chars = _CJK_RE.findall(trigger)
            if len(cjk_chars) < 2:
                continue
            # Skip fuzzy matching for mixed CJK/ASCII triggers
            if _ASCII_RE.search(trigger):
                continue

            # Tier 2: Subsequence — all CJK chars of trigger appear in order
            if _is_subsequence(cjk_chars, q, max_gap=3):
                logger.debug("L1 subsequence match: %r in %r → %s", trigger, q, skill)
                fuzzy_matches.append((trigger, skill))
                continue

            # Tier 3: Regex fuzzy — insert .{0,3} between trigger segments
            segments = re.findall('[\u4e00-\u9fff]+', trigger)
            if len(segments) >= 2:
                pattern = r'.{0,3}'.join(re.escape(s) for s in segments)
                try:
                    if re.search(pattern, q):
                        logger.debug("L1 regex fuzzy match: %r ~ %r → %s", pattern, q, skill)
                        fuzzy_matches.append((trigger, skill))
                except re.error:
                    pass

        if fuzzy_matches:
            # Longest trigger wins, same as Tier 1
            fuzzy_matches.sort(key=lambda x: -len(x[0]))
            return fuzzy_matches[0][1]

        return None


    def _lazy_init(self) -> None:
        self._loading = True
        self._last_init_attempt = time.monotonic()
        try:
            t0 = time.time()
            self._load_skills()
            self._skill_name_to_idx = {
                name: i for i, name in enumerate(self._skill_names)
            }
            self._load_synonyms()
            self._build_fts5_index()
            self._load_embedding_model()
            t1 = time.time()
            self._ready = True
            logger.info(
                "Skill retriever ready: %d skills, %d synonyms, %.1fs",
                len(self._skill_names),
                sum(len(v) for v in self._synonyms.values()),
                t1 - t0,
            )
        except Exception as e:
            self._error = str(e)
            logger.warning("Skill retriever init failed: %s", e)
        finally:
            self._loading = False

    def _load_skills(self) -> None:
        from hermes_constants import get_hermes_home
        skills_dir = get_hermes_home() / "skills"
        hermes_agent_skills = get_hermes_home() / "hermes-agent" / "skills"

        seen = set()
        for base_dir in [skills_dir, hermes_agent_skills]:
            if not base_dir.exists():
                continue
            self._scan_skill_dir(base_dir, seen)

    def _scan_skill_dir(
        self, base_dir: Path, seen: set[str]
    ) -> None:
        """Recursively scan for SKILL.md files — handles flat and nested layouts.

        Flat:   skills/<name>/SKILL.md
        Nested: skills/<category>/<name>/SKILL.md
        """
        for entry in sorted(base_dir.iterdir()):
            if not entry.is_dir():
                continue
            skill_md = entry / "SKILL.md"
            if skill_md.exists():
                name = entry.name
                if name in seen:
                    continue
                try:
                    content = skill_md.read_text(encoding="utf-8")
                    desc = self._extract_description(content)
                    seen.add(name)
                    self._skill_names.append(name)
                    self._skill_descs.append(desc)
                    self._skill_paths[name] = skill_md
                except Exception:
                    pass
            else:
                # Could be a category directory — recurse one level
                has_skill_md = any(
                    (sub / "SKILL.md").exists()
                    for sub in entry.iterdir()
                    if sub.is_dir()
                )
                if has_skill_md:
                    self._scan_skill_dir(entry, seen)

    @staticmethod
    def _extract_description(content: str) -> str:
        if not content.startswith("---"):
            return ""
        parts = content.split("---", 2)
        if len(parts) < 3:
            return ""
        for line in parts[1].split("\n"):
            if line.strip().startswith("description:"):
                return line.strip()[12:].strip().strip("\"'")
        return ""

    def _load_synonyms(self) -> None:
        """Load synonym dictionary — Layer 3 source data."""
        import jieba
        import yaml

        synonym_file = Path(__file__).parent / "skill_synonyms.yaml"
        if not synonym_file.exists():
            logger.debug("No synonym dictionary found at %s", synonym_file)
            return

        try:
            content = synonym_file.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
            if not isinstance(data, dict):
                return

            for skill_name, syns in data.items():
                if not isinstance(syns, list):
                    continue
                for syn in syns:
                    if isinstance(syn, str) and syn.strip():
                        self._synonyms.setdefault(skill_name, []).append(syn.strip())

            # Build reverse index for Layer 3
            valid_names = set(self._skill_names)
            for skill_name, syn_list in self._synonyms.items():
                if skill_name not in valid_names:
                    continue
                for syn in syn_list:
                    # Index jieba tokens of the synonym
                    tokens = [t.strip() for t in jieba.cut(syn) if len(t.strip()) > 1]
                    for token in tokens:
                        self._synonym_index.setdefault(token, []).append(
                            (skill_name, 1.0)
                        )
                    # Also index the full synonym as a single unit
                    if len(syn) > 1:
                        self._synonym_index.setdefault(syn, []).append(
                            (skill_name, 1.5)
                        )

            logger.info(
                "Loaded %d synonym entries for %d skills, %d index tokens",
                sum(len(v) for v in self._synonyms.values()),
                len(self._synonyms),
                len(self._synonym_index),
            )
        except Exception as e:
            logger.warning("Failed to load synonym dictionary: %s", e)

    def _build_fts5_index(self) -> None:
        """Layer 2: Build clean FTS5 index (name + description only)."""
        import jieba

        if not self._jieba_initialized:
            jieba.initialize()
            self._jieba_initialized = True

        all_doc_freq: Counter = Counter()
        for i, desc in enumerate(self._skill_descs):
            name = self._skill_names[i]
            text = f"{name} {desc}"
            tokens = [
                t.strip() for t in jieba.cut(text)
                if len(t.strip()) > 1 and not t.strip().isdigit()
            ]
            self._doc_tokens.append(tokens)
            for token in set(tokens):
                all_doc_freq[token] += 1

        n = len(self._skill_names)
        self._idf = {
            t: math.log((n + 1) / (df + 1)) + 1
            for t, df in all_doc_freq.items()
        }

    def _load_embedding_model(self) -> None:
        """Layer 4: Load dense embedding model.

        Uses an OpenAI-compatible HTTP embedding endpoint (e.g. llama.cpp
        with jina-embeddings-v5) instead of sentence-transformers.  This
        avoids pulling PyTorch into the Hermes venv and lets you serve
        embeddings from a dedicated model server.

        The embedding matrix is cached to disk so that a gateway restart
        does NOT trigger a full re-embedding of all skills via HTTP.  The
        cache is invalidated when skill names/descriptions change or when
        the embedding endpoint URL/model changes.

        Configuration via environment variables:
          HERMES_EMBEDDING_BASE_URL  (default: http://localhost:8080/v1)
          HERMES_EMBEDDING_MODEL     (default: default — llama.cpp ignores it)
          HERMES_EMBEDDING_API_KEY   (default: not-required)
          HERMES_EMBEDDING_BATCH_SIZE (default: 16)
        """
        try:
            import numpy as np
            import requests
        except ImportError:
            logger.warning("numpy/requests not installed; FTS5+Syn only")
            self._emb_matrix = None
            self._emb_error = "numpy/requests not installed"
            return

        base_url = os.environ.get(
            "HERMES_EMBEDDING_BASE_URL",
            "http://localhost:8080/v1",
        )
        api_key = os.environ.get("HERMES_EMBEDDING_API_KEY", "")
        model_name = os.environ.get("HERMES_EMBEDDING_MODEL", "default")
        batch_size = int(os.environ.get("HERMES_EMBEDDING_BATCH_SIZE", "16"))

        self._emb_base_url = base_url
        self._emb_api_key = api_key
        self._emb_model_name = model_name

        # Build a cache key from the skill set + endpoint config.
        # If anything changes (new skill, edited description, different
        # embedding model/URL), the cache is invalidated automatically.
        import hashlib
        texts = [f"{n}, {d}" for n, d in zip(self._skill_names, self._skill_descs)]
        manifest_src = "\n".join(texts) + f"\n{base_url}\n{model_name}"
        cache_key = hashlib.sha256(manifest_src.encode("utf-8")).hexdigest()[:16]

        # Cache path: ~/.hermes/.eagle_eye_emb_cache.npz
        from hermes_constants import get_hermes_home
        cache_path = get_hermes_home() / ".eagle_eye_emb_cache.npz"

        # ── Try disk cache first ──
        if cache_path.exists():
            try:
                cached = np.load(cache_path, allow_pickle=False)
                if str(cached["cache_key"]) == cache_key:
                    self._emb_matrix = cached["embeddings"].astype(np.float32)
                    logger.info(
                        "Embedding cache HIT: loaded %s from disk (%.1fMB)",
                        self._emb_matrix.shape,
                        self._emb_matrix.nbytes / 1e6,
                    )
                    self._emb_ready = True
                    self._emb_error = None
                    return
                else:
                    logger.info("Embedding cache miss: skill set changed, re-embedding")
            except Exception as e:
                logger.debug("Embedding cache read failed: %s", e)

        # ── Cache miss: embed all skills via HTTP in batches ──
        try:
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            all_embeddings: list[list[float]] = []
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                resp = requests.post(
                    f"{base_url}/embeddings",
                    headers=headers,
                    json={"input": batch, "model": model_name},
                    timeout=60,
                )
                resp.raise_for_status()
                data = resp.json()
                # Sort by index to ensure order matches input
                sorted_data = sorted(data["data"], key=lambda x: x["index"])
                for item in sorted_data:
                    all_embeddings.append(item["embedding"])

            self._emb_matrix = np.array(all_embeddings, dtype=np.float32)

            # L2-normalize for cosine similarity via dot product
            norms = np.linalg.norm(self._emb_matrix, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            self._emb_matrix = self._emb_matrix / norms

            # Save to disk cache
            try:
                np.savez(cache_path, embeddings=self._emb_matrix, cache_key=np.array(cache_key))
                logger.info(
                    "Embedding matrix cached to disk: %s (%.1fMB)",
                    cache_path, self._emb_matrix.nbytes / 1e6,
                )
            except Exception as e:
                logger.debug("Could not write embedding cache: %s", e)

            logger.info(
                "Embedding model loaded via HTTP: %s, shape: %s",
                base_url, self._emb_matrix.shape,
            )
            self._emb_ready = True
            self._emb_error = None
        except Exception as e:
            logger.warning("Embedding model load failed (%s); FTS5+Syn only", e)
            self._emb_matrix = None
            self._emb_error = str(e)


    def _retrieve_inner(self, query: str, k: int) -> list[str]:
        """Layers 2-5: FTS5 + Synonym + Embedding → RRF fusion.

        Returns empty list when confidence is too low — meaning the query
        doesn't match any skill well, and the LLM should use general knowledge.
        """
        fts5_results = self._fts5_search(query, k * 3)
        syn_results = self._syn_search(query, k * 3)
        emb_results = self._emb_search(query, k * 3)

        fused = self._rrf_fusion(fts5_results, syn_results, emb_results)

        if not fused:
            return []

        top_score = fused[0][1]

        # Confidence check: top-1 must exceed floor (filter pure noise only)
        if top_score < _CONFIDENCE_THRESHOLD:
            logger.debug(
                "Skill retriever: top-1 score %.4f < floor %.4f, no signal",
                top_score, _CONFIDENCE_THRESHOLD,
            )
            return []

        # No gap check — when multiple skills score close, return all as hints
        # and let the LLM decide which (if any) to load.

        result = []
        for idx, score in fused[:k]:
            if score >= _MIN_RRF_SCORE:
                result.append(self._skill_names[idx])
        return result

    def _fts5_search(self, query: str, k: int) -> list[tuple[int, float]]:
        """Layer 2: Clean BM25 search — name + description only, no synonym mixing."""
        import jieba

        query_tokens = [
            t.strip() for t in jieba.cut(query)
            if len(t.strip()) > 1
        ]
        scores: dict[int, float] = defaultdict(float)

        for qt in query_tokens:
            q_idf = self._idf.get(qt, 1.0)
            for i, doc_tok in enumerate(self._doc_tokens):
                tf = doc_tok.count(qt)
                if tf > 0:
                    scores[i] += q_idf * tf / (tf + 1.5)
                # Direct string match bonus in name+desc
                if qt in f"{self._skill_names[i]} {self._skill_descs[i]}":
                    scores[i] += q_idf * 0.5

        ranked = sorted(scores.items(), key=lambda x: -x[1])
        return ranked[:k]

    def _syn_search(self, query: str, k: int) -> list[tuple[int, float]]:
        """Layer 3: Synonym dictionary matching — independent scoring."""
        import jieba

        query_tokens = [
            t.strip() for t in jieba.cut(query)
            if len(t.strip()) > 1
        ]
        scores: dict[int, float] = defaultdict(float)

        # Token-level synonym matching
        for qt in query_tokens:
            if qt in self._synonym_index:
                q_idf = self._idf.get(qt, 1.0)
                for skill_name, weight in self._synonym_index[qt]:
                    idx = self._skill_name_to_idx.get(skill_name)
                    if idx is not None:
                        scores[idx] += weight * q_idf

        # Full-phrase synonym matching (multi-char synonyms in query)
        for syn_key, entries in self._synonym_index.items():
            if len(syn_key) > 2 and syn_key in query:
                for skill_name, weight in entries:
                    idx = self._skill_name_to_idx.get(skill_name)
                    if idx is not None:
                        scores[idx] += weight * 2.0

        ranked = sorted(scores.items(), key=lambda x: -x[1])
        return ranked[:k]

    def _embed_query(self, query: str):
        """Embed a single query via HTTP, cached by exact query string (LRU, 256 entries)."""
        if self._emb_matrix is None:
            return None
        # Cache hit
        if query in self._query_emb_cache:
            self._query_emb_cache.move_to_end(query)
            return self._query_emb_cache[query]
        # Cache miss: fetch via HTTP
        import numpy as np
        import requests
        try:
            headers = {"Content-Type": "application/json"}
            if self._emb_api_key:
                headers["Authorization"] = f"Bearer {self._emb_api_key}"
            resp = requests.post(
                f"{self._emb_base_url}/embeddings",
                headers=headers,
                json={"input": [query], "model": self._emb_model_name},
                timeout=30,
            )
            resp.raise_for_status()
            query_emb = np.array(resp.json()["data"][0]["embedding"], dtype=np.float32)
            norm = np.linalg.norm(query_emb)
            if norm > 0:
                query_emb = query_emb / norm
        except Exception as e:
            logger.debug("Embedding query failed: %s", e)
            return None
        # Store in cache
        self._query_emb_cache[query] = query_emb
        if len(self._query_emb_cache) > self._query_emb_cache_max:
            self._query_emb_cache.popitem(last=False)
        return query_emb

    def _emb_search(self, query: str, k: int) -> list[tuple[int, float]]:
        """Layer 4: Dense embedding cosine similarity via HTTP endpoint."""
        if self._emb_matrix is None:
            return []
        import numpy as np
        query_emb = self._embed_query(query)
        if query_emb is None:
            return []
        scores = np.dot(self._emb_matrix, query_emb.T).flatten()
        top_idx = np.argsort(-scores)[:k]
        return [(int(idx), float(scores[idx])) for idx in top_idx]

    @staticmethod
    def _rrf_fusion(
        fts5_results: list[tuple[int, float]],
        syn_results: list[tuple[int, float]],
        emb_results: list[tuple[int, float]],
        k: int = _RRF_K,
    ) -> list[tuple[int, float]]:
        """Layer 5: Reciprocal Rank Fusion of three ranked lists."""
        fused: dict[int, float] = {}

        for rank, (idx, _) in enumerate(fts5_results, start=1):
            fused[idx] = fused.get(idx, 0.0) + _RRF_W_FTS5 / (k + rank)

        for rank, (idx, _) in enumerate(syn_results, start=1):
            fused[idx] = fused.get(idx, 0.0) + _RRF_W_SYN / (k + rank)

        for rank, (idx, _) in enumerate(emb_results, start=1):
            fused[idx] = fused.get(idx, 0.0) + _RRF_W_EMB / (k + rank)

        return sorted(fused.items(), key=lambda x: -x[1])

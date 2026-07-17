# Changelog

All notable changes to this project will be documented in this file.

## [1.3.0] - 2026-07-17

### Changed
- Single config CLI: `scripts/build_config.py` (shims keep old names)
- Skip hidden skill dirs (`.archive`, …); short-ASCII L1 word boundaries
- L1 empty-content fallback; quieter emb init log
- install prefers existing config / hermes enable (no yaml.dump thrash)
- Incremental embedding cache (v2): per-skill hash reuse, v1 migrate, process lock, atomic write
- Drop L1 hard triggers for skills missing after live scan (stale/orphan safety)
- Repo cleanup: drop PROMPTS_*, example template, dual generator path
- Spec Kit: constitution v1.0.0 + specs/001-lean-reliable-core



## [1.2.0] - 2026-07-08

### Changed
- **L1 direct injection**: Hard trigger hits now inject skill content directly into context (capped at 4000 chars), eliminating the `skill_view()` round-trip. Truncated skills include a note pointing to `skill_view()` for full content
- **L2-5 richer hints**: Hint bullets now include skill descriptions (`- **name** — desc`) so the LLM can judge relevance without loading each skill
- **Noise filter**: System-injected messages (`[ASYNC DELEGATION]`, `Review the conversation above`, `[Replying to:`, `[System`, `[Balázs`) are skipped before retrieval — no more false fires on non-user messages
- L1 matches skip `skill_view()` / `skill_usage.bump_use()` — deterministic matches don't need curator tracking
- L2-5 header includes `(Degraded: semantic search unavailable)` when embedding layer is down

### Added
- `get_skill_desc()` method on `SkillRetriever` — O(1) description lookup via `_skill_name_to_idx`
- Query embedding cache (OrderedDict, 256 entries, LRU eviction)
- Embedding readiness tracking with degraded mode logging
- Embedding health check logged at plugin startup

## [1.1.0] - 2026-07-02

### Changed
- **Breaking**: Replaced `sentence-transformers` with HTTP-based embeddings (OpenAI-compatible `/v1/embeddings` endpoint)
  - Removed PyTorch dependency (~2GB), reducing memory footprint from ~403MB to ~50MB
  - Added `HERMES_EMBEDDING_BASE_URL`, `HERMES_EMBEDDING_MODEL`, `HERMES_EMBEDDING_API_KEY` env vars
  - Embeddings batched in groups of 16 to avoid overwhelming the endpoint
  - L2-normalized embedding matrix for cosine similarity via dot product
- Fixed skill discovery to handle both flat (`skills/<name>/SKILL.md`) and nested (`skills/<category>/<name>/SKILL.md`) directory layouts via recursive scanning
- Updated `install.sh` to install `jieba numpy requests` instead of `jieba sentence-transformers`
- Increased init wait timeout from 30s to 120s for HTTP embedding latency
- Updated `plugin.yaml` version to 1.1.0

### Added
- `scripts/build_real_config.py` — generates real hard triggers and synonyms from skill names and descriptions (the original `generate_config.py` only produced TODO templates)
- Hard triggers now loaded from external `hard_triggers_generated.py` file at import time (keeps user-specific triggers separate from engine code)
- `.gitignore` for generated/user-specific files
- README "Changes from upstream" section
- ARCHITECTURE.md section 3.4: Coexistence with Hermes Skill Index

## [1.0.0] - 2026-06-01

### Initial Release
- 5-layer retrieval architecture: Hard Triggers → FTS5 → Synonym → Embedding → RRF
- 3-tier hard trigger matching: exact substring → subsequence → regex fuzzy
- Independent synonym dictionary layer with jieba tokenization
- Dense embedding via configurable sentence-transformers model
- Reciprocal Rank Fusion with k=60 dampening
- Confidence gate to prevent forced matches
- Zero-invasive plugin architecture (pre_llm_call hook)
- Graceful degradation: each layer fails independently
- Auto-config generator script (scans local skill library)
- Bilingual LLM prompts for generating triggers and synonyms
- Bilingual documentation (English + Chinese)

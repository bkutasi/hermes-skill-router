# Changelog

All notable changes to this project will be documented in this file.

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

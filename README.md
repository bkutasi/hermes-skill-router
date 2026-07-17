# 🦅 Eagle Eye — 5-Layer Intelligent Skill Retrieval for Hermes Agent

> **Narrow 100+ skills down to the right 5 — deterministic triggers, fuzzy matching, semantic search, and rank fusion. Zero core modification.**

Fork of [willingning-coder/eagle-eye](https://github.com/willingning-coder/eagle-eye) with HTTP-based embeddings, flat directory support, and a real config generator.

---

## The Problem

[Hermes Agent](https://github.com/nousresearch/hermes-agent) loads every installed skill into the system prompt as a flat list. When you have 50+ skills:

- **The LLM picks wrong** — overlapping descriptions confuse selection
- **You burn tokens** — 5,000–10,000 tokens per turn just for the skill list
- **Rarely-used skills become invisible** — buried at the bottom of a long list

## The Solution

Eagle Eye is a **zero-invasive plugin** that acts as an intelligent pre-filter. Before each API call, it narrows the skill list to the top-5 most relevant candidates and injects them as a lightweight hint.

```
User Query
    │
    ▼
┌─────────────────────────────────────────────┐
│  L1: Hard Triggers                          │
│  Deterministic keyword matching (3-tier)    │
│  Hit → Inject full SKILL.md instantly       │
│  Miss ↓                                     │
├─────────────────────────────────────────────┤
│  L2: FTS5 BM25     (text similarity)        │
│  L3: Synonym Dict   (domain knowledge)      │
│  L4: Dense Embedding (semantic similarity)  │
│  L5: RRF Fusion     (rank combination)      │
│                                             │
│  Score ≥ threshold → Inject skill hints     │
│  Score < threshold → Silent (LLM decides)   │
└─────────────────────────────────────────────┘
    │
    ▼
LLM Final Decision
```

## Key Design Decisions

### 1. "Not matching" is a valid result

Not every query needs a skill. "What should I eat for dinner?" is best answered by the LLM's general knowledge — not by loading a restaurant-finder skill. Eagle Eye's confidence gate prevents forced matches.

### 2. Deterministic first, probabilistic second

L1 (hard triggers) is 100% precise — if the user types "debug", the debugging skill loads instantly with no probability involved. L2–L5 handles the long tail where fuzzy, semantic matching adds value.

### 3. Hints, not decisions

L2–L5 returns candidates, not conclusions. The LLM retains final authority to load a skill, combine multiple skills, or ignore the hint entirely. The retrieval system doesn't override the LLM's judgment.

### 4. Each layer fails independently

If the embedding endpoint is down, L4 degrades gracefully — L1+L2+L3 still work. If `jieba` is missing, L1+L4 still work. The system never crashes; it always falls back to a working subset.

### 5. Coexist with the full skill index

Eagle Eye does **not** replace Hermes' built-in skill index in the system prompt. Both layers work together — the full index stays as a safety net, while Eagle Eye adds high-confidence matches and semantic hints on top. This preserves the skill curator's ability to track usage and improve skills over time.

## Quick Start

```bash
# 1. Clone
git clone https://github.com/bkutasi/eagle-eye.git
cd eagle-eye

# 2. Generate config from your local skill library
python scripts/build_config.py

# 3. Review if needed
#    - src/hard_triggers_generated.py
#    - src/skill_synonyms.yaml

# 4. Install
bash scripts/install.sh

# 5. Restart Hermes
hermes gateway restart
```

## Customization

Eagle Eye ships with **minimal example data**. The real power comes from generating your own configuration based on your installed skills.

### Auto-Generate (Recommended)

```bash
python scripts/build_config.py              # triggers + synonyms
python scripts/build_config.py --scan-only  # list skills
```

### Manual Customization

| Component | File | What to do |
|-----------|------|------------|
| **Hard Triggers** | `src/hard_triggers_generated.py` | Add `(keyword, skill-name)` tuples. More specific first. |
| **Synonym Dictionary** | `src/skill_synonyms.yaml` | Map natural language terms to skills. 5–15 per skill. |
| **Embedding Endpoint** | `HERMES_EMBEDDING_BASE_URL` env var | Point to your OpenAI-compatible embedding server. |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HERMES_DISABLE_SKILL_RETRIEVAL` | *(unset)* | Set `1` to disable entirely |
| `HERMES_SKILL_RETRIEVAL_TOP_K` | `5` | Number of skills to return |
| `HERMES_EMBEDDING_BASE_URL` | `http://localhost:8080/v1` | OpenAI-compatible embedding API base URL |
| `HERMES_EMBEDDING_MODEL` | `default` | Model name for embedding API |
| `HERMES_EMBEDDING_API_KEY` | *(unset)* | API key for embedding endpoint (if required) |

## Performance

| Metric | Value |
|--------|-------|
| L1 real-world accuracy | ~90% |
| Functional test accuracy | 100% |
| Query latency (cached) | ~20ms + ~200ms HTTP embedding call |
| First-call latency | ~40-60s (batch embedding of all skills) |
| Memory footprint | ~50MB (embedding matrix only, no local model) |

## Architecture

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for a deep technical dive covering:

- Layer-by-layer algorithm analysis with code
- RRF fusion math and why it beats score normalization
- Confidence gate design philosophy
- Failure mode matrix and degradation hierarchy
- Latency and memory profiling

## File Structure

```
eagle-eye/
├── src/
│   ├── skill_retriever.py           # 5-layer retrieval engine
│   ├── plugin.py                    # pre_llm_call hook
│   ├── plugin.yaml
│   ├── hard_triggers_generated.py   # generated (gitignored)
│   └── skill_synonyms.yaml          # generated (gitignored)
├── scripts/
│   ├── build_config.py              # only config generator
│   ├── install.sh
│   ├── build_real_config.py         # shim → build_config
│   └── generate_config.py           # shim → build_config
├── tests/
├── docs/embedding-server.md
├── README.md / README_CN.md
├── ARCHITECTURE.md
├── CHANGELOG.md
└── LICENSE
```

## Dependencies

| Package | Required? | Purpose |
|---------|-----------|---------|
| `jieba` | Yes | Chinese tokenization for L2–L3 |
| `numpy` | Yes | Numerical operations for L4 (embedding matrix) |
| `requests` | Yes | HTTP calls to embedding endpoint for L4 |
| An embedding server | Optional | Any OpenAI-compatible `/v1/embeddings` endpoint (llama.cpp, vLLM, Ollama, etc.) |

> **Note:** This fork replaces `sentence-transformers` with HTTP-based embeddings. See [Changes from upstream](#changes-from-upstream) below.

## Changes from upstream

This fork is based on [willingning-coder/eagle-eye](https://github.com/willingning-coder/eagle-eye) v1.0.0 and includes the following changes:

### v1.1.0 — HTTP Embeddings + Flat Directory Support

**Breaking: Embedding backend changed from local model to HTTP API**

- **Replaced `sentence-transformers` with HTTP-based embeddings.** The embedding layer (L4) now calls an OpenAI-compatible `/v1/embeddings` endpoint instead of loading a local PyTorch model. This removes the PyTorch dependency (~2GB), reduces memory footprint from ~403MB to ~50MB, and lets you use any embedding model served via llama.cpp, vLLM, Ollama, Infinity, or any OpenAI-compatible API.
  - Configure via `HERMES_EMBEDDING_BASE_URL`, `HERMES_EMBEDDING_MODEL`, `HERMES_EMBEDDING_API_KEY` env vars.
  - Embeddings are batched in groups of 16 to avoid overwhelming the endpoint.
  - The embedding matrix is L2-normalized at init time; query embeddings are normalized at search time for cosine similarity via dot product.

- **Fixed skill discovery for flat directory layouts.** The original code only handled `skills/<category>/<skill_name>/SKILL.md` (nested). Now also handles `skills/<skill_name>/SKILL.md` (flat) via recursive scanning. Both layouts can coexist in the same skills directory.

- **Single config surface `scripts/build_config.py`** — real hard triggers + synonyms from skill tree (manual overrides + name triggers). Old `generate_config` / `build_real_config` names are shims.

- **Triggers loaded from external file.** `_HARD_TRIGGERS` is now loaded at import time from `hard_triggers_generated.py` (auto-generated, gitignored). This keeps user-specific triggers separate from the engine code.

- **Increased init wait timeout** from 30s to 120s to accommodate HTTP embedding latency for large skill libraries (230+ skills take ~40-60s to embed in batches).

- **Updated `install.sh`** to install `jieba numpy requests` instead of `jieba sentence-transformers`.

- **Added `.gitignore`** for generated/user-specific files.

## Contributing

Contributions are welcome! Areas where help is especially valuable:

- **Trigger/synonym quality**: Share your `_HARD_TRIGGERS` and `skill_synonyms.yaml` configurations
- **Embedding model benchmarks**: Test alternative models and report accuracy
- **Multi-language support**: Extend triggers and synonyms beyond Chinese/English
- **Bug reports**: Edge cases in fuzzy matching, false positives/negatives

## License

[MIT](LICENSE)

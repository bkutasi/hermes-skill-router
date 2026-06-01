# 🦅 Eagle Eye — 5-Layer Intelligent Skill Retrieval for Hermes Agent

> **Narrow 100+ skills down to the right 5 — deterministic triggers, fuzzy matching, semantic search, and rank fusion. Zero core modification.**

[中文文档](README_CN.md)

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

If `sentence-transformers` isn't installed, L4 degrades gracefully — L1+L2+L3 still work. If `jieba` is missing, L1+L4 still work. The system never crashes; it always falls back to a working subset.

## Quick Start

```bash
# 1. Clone
git clone https://github.com/willingning-coder/eagle-eye.git
cd eagle-eye

# 2. Generate config from your local skill library
python scripts/generate_config.py

# 3. Review and customize
#    - Edit _HARD_TRIGGERS in src/skill_retriever.py
#    - Edit src/skill_synonyms.yaml
#    (See PROMPTS.md for LLM-assisted generation)

# 4. Install
bash scripts/install.sh

# 5. Restart Hermes
hermes gateway restart
```

## Customization

Eagle Eye ships with **minimal example data**. The real power comes from generating your own configuration based on your installed skills.

### Auto-Generate (Recommended)

```bash
# Scan your skills and generate template configs
python scripts/generate_config.py

# Or just list what was found
python scripts/generate_config.py --scan-only
```

### Manual Customization

| Component | File | What to do |
|-----------|------|------------|
| **Hard Triggers** | `src/skill_retriever.py` → `_HARD_TRIGGERS` | Add `(keyword, skill-name)` tuples. More specific first. |
| **Synonym Dictionary** | `src/skill_synonyms.yaml` | Map natural language terms to skills. 5–15 per skill. |
| **Embedding Model** | `HERMES_EMBEDDING_MODEL` env var | Swap to a different sentence-transformers model. |

### LLM-Assisted Generation

Use the prompts in [`PROMPTS_EN.md`](PROMPTS_EN.md) or [`PROMPTS_CN.md`](PROMPTS_CN.md) with any LLM to generate high-quality triggers and synonyms from your skill list.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HERMES_DISABLE_SKILL_RETRIEVAL` | *(unset)* | Set `1` to disable entirely |
| `HERMES_SKILL_RETRIEVAL_TOP_K` | `5` | Number of skills to return |
| `HERMES_EMBEDDING_MODEL` | `shibing624/text2vec-base-chinese-paraphrase` | Embedding model for L4 |

## Performance

| Metric | Value |
|--------|-------|
| L1 real-world accuracy | ~90% |
| Functional test accuracy | 100% |
| Query latency (cached) | ~20ms |
| First-call latency | ~11s (model loading) |
| Memory footprint | ~403MB (with embedding) |

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
│   ├── skill_retriever.py      # Core 5-layer retrieval engine
│   ├── skill_synonyms.yaml     # Synonym dictionary (template)
│   ├── plugin.py               # Hermes plugin (pre_llm_call hook)
│   └── plugin.yaml             # Plugin manifest
├── scripts/
│   ├── generate_config.py      # Auto-generate config from your skills
│   └── install.sh              # One-command installation
├── templates/
│   └── hard_triggers.example.py  # Trigger format reference
├── README.md                   # This file (English)
├── README_CN.md                # 中文文档
├── ARCHITECTURE.md             # Technical deep dive
├── PROMPTS_EN.md               # LLM prompts for config generation (English)
├── PROMPTS_CN.md               # LLM prompts for config generation (中文)
├── CHANGELOG.md                # Version history
└── LICENSE                     # MIT
```

## Dependencies

| Package | Required? | Purpose |
|---------|-----------|---------|
| `jieba` | Yes | Chinese tokenization for L2–L3 |
| `sentence-transformers` | Optional | Dense embedding for L4 (graceful fallback if missing) |
| `numpy` | Optional | Numerical operations for L4 |

## Contributing

Contributions are welcome! Areas where help is especially valuable:

- **Trigger/synonym quality**: Share your `_HARD_TRIGGERS` and `skill_synonyms.yaml` configurations
- **Embedding model benchmarks**: Test alternative models and report accuracy
- **Multi-language support**: Extend triggers and synonyms beyond Chinese/English
- **Bug reports**: Edge cases in fuzzy matching, false positives/negatives

## License

[MIT](LICENSE)

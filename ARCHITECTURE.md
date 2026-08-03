# Architecture

## Contract

Hermes user plugin only. Hook: `pre_llm_call` → return `{"context": "..."}`
into the user message path. No core skill-list replacement.

| Layer | Job | Fail mode |
|-------|-----|-----------|
| L1 | Hard triggers → strong canonical `skill_view()` hint | Skip until init ready |
| L2 | In-memory BM25 on name+description (jieba tokens) | Empty if no tokens |
| L3 | Synonym reverse index | Empty if no yaml |
| L4 | HTTP embeddings, cosine via L2-normalized matrix | Degrade to L2+L3 |
| L5 | Weighted RRF; confidence floor | Return no hints |

## Init (per process)

1. Scan `~/.hermes/skills` + `~/.hermes/hermes-agent/skills` (skip `.*` dirs; nested packages under a parent `SKILL.md` counted).
2. Filter hard triggers to live skill names.
3. **Text index cache** (`~/.hermes/.hermes_skill_router_text_index.npz`): load synonyms + BM25 if skill/syn key matches; else build (jieba) and write.
4. **Emb cache** (`~/.hermes/.hermes_skill_router_emb_cache.npz`): full HIT, or partial row reuse by name+text hash, else HTTP batch. Process lock + atomic write.

Measured (≈227 skills): cold build ~0.3–0.4s; warm process ready **~15ms** with both caches HIT.

## L1 matching

- Short single-token ASCII (len ≤ 8, no space): word-boundary + case-insensitive.
- Longer / multi-word: case-insensitive substring.
- CJK: subsequence + optional fuzzy segments; mixed CJK/ASCII skips fuzzy.
- Longest trigger wins; ties → earliest position.

## L2–5 scoring

RRF weights (code): FTS 0.45, synonym 0.35, emb 0.20, k=60.
Min RRF score and top-1 confidence floor drop pure noise.

## Config generation

`scripts/build_config.py` only:

- Manual high-confidence keywords for known skills.
- Auto name-trigger only for long hyphenated names (`len≥10` and `-`) to avoid English false L1.
- Synonyms from name parts + description keywords + manuals.

Then `bash scripts/install.sh` copies into `~/.hermes/plugins/hermes-skill-router/` and retires the legacy `eagle-eye` identity.

## Non-goals

Local sentence-transformers, SQLite FTS rewrite, hot-reload without process restart.

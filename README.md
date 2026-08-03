# Hermes Skill Router

Narrow a large skill library to the few that matter **before** the model call.
Zero Hermes core patches: one user plugin, `pre_llm_call` hook only.

An independently maintained Hermes plugin, evolved from the original Eagle Eye
concept with a rewritten retrieval pipeline, HTTP embeddings, durable caches,
nested skill discovery, and safe plugin migration.

## How it works

```
User message
    │
    ▼
 L1 hard triggers  →  hit: inject one strong skill_view hint
    │ miss
    ▼
 L2 BM25 (name+desc) + L3 synonyms + L4 HTTP emb  →  RRF (L5)
    │
    ▼ score ok → inject name+desc hints
      score low → silent (general knowledge)
```

- **L1**: deterministic keyword match that routes through canonical `skill_view()`.
- **L2–5**: ranking only — the model still chooses `skill_view()` or ignore.
- **Degrade**: emb down → L2+L3; never crash the turn.
- **Coexist**: does not remove Hermes’ full skill index.

## Quick start

```bash
git clone https://github.com/bkutasi/hermes-skill-router.git
cd hermes-skill-router

# optional: point at your emb server (see docs/embedding-server.md)
# echo 'HERMES_EMBEDDING_BASE_URL=http://localhost:3001/v1' >> ~/.hermes/.env

python scripts/build_config.py   # triggers + synonyms from live skills
bash scripts/install.sh
hermes gateway restart           # process must reload plugin code
```

Disable: `HERMES_DISABLE_SKILL_RETRIEVAL=1`.

## Operator loop

| When | What |
|------|------|
| Skills added/archived | `python scripts/build_config.py && bash scripts/install.sh && hermes gateway restart` |
| Emb URL/model change | restart after env change; emb cache key includes URL |
| Check health | logs: `Text index cache HIT` / `Embedding cache HIT` / `Skill retriever ready` |

Caches (under `~/.hermes/`):

| File | Purpose |
|------|---------|
| `.hermes_skill_router_text_index.npz` | synonyms + BM25 tokens (avoids jieba rebuild every process) |
| `.hermes_skill_router_emb_cache.npz` | dense matrix; row reuse when only some skills change |

## Layout

```
src/
  plugin.py                 # pre_llm_call hook
  skill_retriever.py        # L1–5 + caches
  plugin.yaml
  hard_triggers_generated.py  # generated (gitignored)
  skill_synonyms.yaml         # generated (gitignored)
scripts/
  build_config.py           # only generator
  install.sh
tests/
docs/embedding-server.md    # this host’s emb endpoint notes
ARCHITECTURE.md             # design notes
```

## Env

| Variable | Default | Notes |
|----------|---------|--------|
| `HERMES_EMBEDDING_BASE_URL` | `http://localhost:8080/v1` | Must match a live OpenAI-compatible emb API |
| `HERMES_EMBEDDING_MODEL` | `default` | |
| `HERMES_EMBEDDING_API_KEY` | empty | |
| `HERMES_EMBEDDING_BATCH_SIZE` | `16` | |
| `HERMES_EMBEDDING_TIMEOUT_SECONDS` | `2` | Bounds local HTTP failure latency |
| `HERMES_SKILL_RETRIEVAL_TOP_K` | `5` | |
| `HERMES_DISABLE_SKILL_RETRIEVAL` | unset | `1` to off |

## Dependencies

`jieba` `numpy` `requests` (install.sh puts them in Hermes venv).

## Tests

```bash
~/.hermes/hermes-agent/venv/bin/python -m pytest tests/ -q
```

## License

MIT

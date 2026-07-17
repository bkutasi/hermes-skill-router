<!--
Sync Impact Report
- Version: (none) → 1.0.0
- Principles: filled from eagle-eye prod reality (lean plugin)
- Templates: not rewritten (still generic Spec Kit defaults)
- Deferred: none
-->

# Eagle Eye Constitution

## Core Principles

### I. Pure plugin, zero core fork
Eagle Eye MUST load only as a Hermes user plugin (`pre_llm_call` → `{"context": ...}`).
MUST NOT patch Hermes core skill lists or replace the system skill index.
Rationale: survives Hermes upgrades; uninstall is delete+disable.

### II. One surface per concern
- Runtime: `src/skill_retriever.py` + `src/plugin.py`
- Config gen: `scripts/build_config.py` only (other script names are shims)
- Install: `scripts/install.sh` copies files; MUST avoid full-config `yaml.dump` thrash
MUST NOT add a second generator, second cache format family, or parallel install path without deleting the old one.

### III. Fail soft, stay fast
- L1 must return instantly (no network)
- L2–5 may degrade (emb down → FTS+syn only; never crash the agent turn)
- Kill switch: `HERMES_DISABLE_SKILL_RETRIEVAL=1`
- Cold restart with unchanged skills MUST use emb disk cache HIT (sub-second emb load)
- Skill-tree churn MUST re-embed only changed rows (cache v2)

### IV. Index only live skills
Scanner MUST skip hidden dirs (`.archive`, `.hub`, …).
Generated triggers MUST NOT target skills missing from the live path map.
Orphan triggers after regen MUST be 0.

### V. Minimal contract tests
pytest MUST cover: L1 word-boundary short ASCII, hidden-dir skip, RRF/confidence contracts, disable switch.
No new deps for tests. Mock only what blocks import.

## Product constraints

- L1: hard trigger → direct SKILL.md inject, cap 4000 chars; empty body → hint-only
- L2–5: name + description hints only; LLM decides `skill_view()`
- Noise: skip system/async/reply prefixes before retrieval
- Dual skill roots OK: `~/.hermes/skills` + `~/.hermes/hermes-agent/skills`
- Default emb URL may stay generic; production MUST set `HERMES_EMBEDDING_BASE_URL` in Hermes env

## Non-goals (MUST NOT ship)

- Local sentence-transformers / torch in Hermes venv
- SQLite FTS rewrite of BM25 layer
- Speculative new retrieval layers
- Hot-reload without process restart (document restart instead)

## Governance

Constitution supersedes ad-hoc “nice to have” scope.
Amendments: bump version (semver), set Last Amended, one-line rationale in CHANGELOG if behavior changes.
PRs/changes that add surfaces without deleting old ones violate II.

**Version**: 1.0.0 | **Ratified**: 2026-07-17 | **Last Amended**: 2026-07-17

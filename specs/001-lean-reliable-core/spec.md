# Feature Specification: Lean Reliable Core

**Feature Branch**: `001-lean-reliable-core`
**Created**: 2026-07-17
**Status**: Draft
**Input**: Make eagle-eye a lean, minimal, reliable, fast plugin; find bugs; keep surfaces small.

## User Scenarios & Testing

### User Story 1 - Fast restart after skill churn (Priority: P1)

Operator restarts Hermes after adding/editing a few skills. Most embeddings reload from disk; only changed skills hit the network. Agent turns keep working if emb is slow/down.

**Why this priority**: 30–80s full re-embeds were the main reliability hit.

**Independent Test**: Seed emb cache for N skills; change 1 description; reload retriever → exactly 1 HTTP embed (or 0 on full HIT); process start under 2s to ready when HIT.

**Acceptance Scenarios**:

1. **Given** unchanged skill set + valid cache, **When** retriever starts, **Then** emb cache HIT and emb ready without HTTP.
2. **Given** one skill text change + v2 cache, **When** retriever starts, **Then** only that skill is re-embedded; others reused.
3. **Given** emb endpoint down, **When** user query has no L1 hit, **Then** L2–3 still may hint or return none — no exception to Hermes.

---

### User Story 2 - No dead skills in routing (Priority: P1)

Archived or hidden skills never get L1 inject or pollute ranking.

**Independent Test**: Place skill under `.archive/`; scan → not in paths; triggers for that name absent after regen; query that name does not inject archive content.

**Acceptance Scenarios**:

1. **Given** `skills/.archive/dead/SKILL.md`, **When** scan runs, **Then** dead not indexed.
2. **Given** regen via build_config, **When** counting orphan triggers, **Then** count is 0.

---

### User Story 3 - Predictable L1 (Priority: P2)

Short accidental substrings do not fire hard triggers; real keywords do.

**Independent Test**: `debug` in `debugging` no L1; bare `debug` L1 to systematic-debugging (if trigger present).

**Acceptance Scenarios**:

1. **Given** short ASCII trigger `debug`, **When** query contains `debugging` only as longer word, **Then** no L1 on `debug`.
2. **Given** L1 hit before paths ready, **When** content empty, **Then** hint-only context (no empty inject).

---

### User Story 4 - One way to operate (Priority: P2)

Operator has one regen command and one install command; docs match.

**Independent Test**: README and install footer mention only `build_config.py`; shims still call it.

**Acceptance Scenarios**:

1. **Given** clean tree, **When** `python scripts/build_config.py` then `bash scripts/install.sh`, **Then** plugin dir hashes match src for runtime files.

### Edge Cases

- Concurrent gateway + CLI both init emb → lock prevents double full re-embed storms
- v1 cache (embeddings only) migrates without full HTTP when order stable
- Skill count changes between user root and bundled root → partial reuse by name+hash
- Disable env set → no bg init, retrieve empty

## Requirements

### Functional Requirements

- **FR-001**: System MUST skip skill directories whose names start with `.`
- **FR-002**: System MUST load emb matrix from disk when skill text hashes + endpoint match
- **FR-003**: System MUST re-embed only skills whose name+text hash is missing from cache
- **FR-004**: System MUST use a process lock around emb miss work
- **FR-005**: System MUST write emb cache atomically
- **FR-006**: Short single-token ASCII L1 triggers (len ≤ 8, no space) MUST match on word boundaries
- **FR-007**: L1 empty content MUST fall back to name/desc hint
- **FR-008**: Config generation MUST use a single primary script surface
- **FR-009**: Install MUST not rewrite whole Hermes config when plugin already listed
- **FR-010**: System MUST NOT crash the agent turn on emb/network failure

### Key Entities

- **Skill**: name, description, SKILL.md path
- **Hard trigger**: keyword to skill name
- **Emb cache v2**: embeddings, cache_key, names, text_hashes, base_url, model

## Success Criteria

- **SC-001**: Unchanged restart emb path completes in under 1 second on this host
- **SC-002**: Single skill edit causes at most one skill worth of HTTP embed work
- **SC-003**: After regen, orphan triggers = 0 and archive-indexed = 0
- **SC-004**: pytest suite stays green with no new runtime dependencies
- **SC-005**: One documented operator loop: build_config, install, restart

## Assumptions

- Hermes loads `~/.hermes/.env` for emb URL in gateway
- Operator restarts after install (no hot reload)
- 200–300 skills is the design scale
- Bundled hermes-agent skills root remains intentional

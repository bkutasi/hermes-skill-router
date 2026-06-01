# Architecture Deep Dive

This document provides a detailed technical explanation of Eagle Eye's 5-layer skill retrieval system.

## 1. Problem Statement

Hermes Agent loads all available skills into the system prompt as a flat list. When the list exceeds ~50 skills, two problems emerge:

1. **Selection accuracy degrades**: LLMs struggle to pick the right skill from a long list, especially when skills have overlapping descriptions
2. **Token waste**: Each skill description consumes ~50-100 tokens. With 100+ skills, that's 5,000-10,000 tokens per turn just for the skill list

The retrieval system acts as a **pre-filter**: before each API call, it narrows the skill list down to the top-5 most relevant candidates, injected as a `[Skill Retrieval Hint]` into the user message.

## 2. Layer-by-Layer Analysis

### 2.1 Layer 1: Hard Triggers

**Purpose**: Instant, deterministic matching for high-confidence keyword→skill mappings.

**Data structure**: A flat list of `(trigger_keyword, skill_name)` tuples, ordered by specificity.

**3-tier matching algorithm**:

```python
def _hard_trigger(query: str) -> str | None:
    # Tier 1: Exact substring (O(n×m) where n=len(query), m=len(trigger))
    for trigger, skill in _HARD_TRIGGERS:
        if trigger in query:
            return skill

    # Tier 2: Subsequence (O(n) per trigger)
    for trigger, skill in _HARD_TRIGGERS:
        cjk_chars = extract_cjk(trigger)
        if len(cjk_chars) >= 2 and is_subsequence(cjk_chars, query):
            return skill

    # Tier 3: Regex fuzzy (O(n) per trigger via re.search)
    for trigger, skill in _HARD_TRIGGERS:
        segments = extract_cjk_segments(trigger)
        if len(segments) >= 2:
            pattern = '.{0,3}'.join(re.escape(s) for s in segments)
            if re.search(pattern, query):
                return skill

    return None
```

**Key design choices**:
- **Longest trigger wins**: When multiple triggers match, the most specific (longest) one is selected
- **Fuzzy matching guards**: Triggers with <2 CJK characters or mixed CJK/ASCII skip fuzzy matching to prevent false positives
- **First match fallback**: For triggers of equal length, the one appearing earliest in the query wins

### 2.2 Layer 2: FTS5 BM25 Text Search

**Purpose**: Keyword-based text matching using Chinese tokenization (jieba).

**Scoring**: BM25-like saturation with direct string match bonus:
```python
score += q_idf * tf / (tf + 1.5)  # BM25 saturation
if qt in f"{name} {desc}":
    score += q_idf * 0.5           # Direct match bonus
```

**Key design choice**: Layer 2 does NOT include synonym tokens in the index. Synonyms are handled by Layer 3 as a separate signal. This keeps the FTS5 index clean and prevents synonym noise from polluting text matching.

### 2.3 Layer 3: Synonym Dictionary

**Purpose**: Domain knowledge encoding — mapping related concepts to skills.

**Two-level matching**:
1. **Token-level**: jieba tokens of each synonym are indexed individually (weight 1.0)
2. **Full-phrase**: multi-character synonyms are also indexed as single units (weight 1.5)

**Why separate from FTS5?**
1. **Different signal types**: FTS5 measures text similarity; synonyms measure conceptual relatedness
2. **Independent tunability**: You can adjust `_RRF_W_SYN` without affecting text matching
3. **Maintainability**: Adding a synonym doesn't require rebuilding the FTS5 index
4. **Debuggability**: You can inspect which layer contributed what score

### 2.4 Layer 4: Dense Embedding

**Purpose**: Semantic similarity for cases where keywords and synonyms miss.

**Default model**: `shibing624/text2vec-base-chinese-paraphrase` (768-dim, ~400MB)

**Customization**: Set `HERMES_EMBEDDING_MODEL` environment variable to use a different model.

**Known limitations**:
- Generic model not fine-tuned for skill matching
- Short queries (<5 chars) produce noisy embeddings
- First query incurs ~10s model loading overhead
- Adds ~400MB memory footprint

**Degradation**: If `sentence-transformers` is not installed or model loading fails, the system gracefully falls back to FTS5+Synonym (Layers 2-3 only).

### 2.5 Layer 5: Reciprocal Rank Fusion

**Purpose**: Combine rankings from Layers 2-4 into a single ranking.

**Algorithm** (from Cormack, Clarke, Butt, 2009):

```python
def rrf_fusion(fts5_results, syn_results, emb_results, k=60):
    fused = {}
    for rank, (idx, _) in enumerate(fts5_results, start=1):
        fused[idx] = fused.get(idx, 0) + 0.45 / (k + rank)
    for rank, (idx, _) in enumerate(syn_results, start=1):
        fused[idx] = fused.get(idx, 0) + 0.35 / (k + rank)
    for rank, (idx, _) in enumerate(emb_results, start=1):
        fused[idx] = fused.get(idx, 0) + 0.20 / (k + rank)
    return sorted(fused.items(), key=lambda x: -x[1])
```

**Why RRF over score fusion?**

| Approach | Problem |
|----------|---------|
| Score normalization | BM25 scores are unbounded, cosine is [0,1] — normalization is fragile |
| Learned fusion weights | Requires training data we don't have |
| Simple voting | Loses ranking information (Top-1 and Top-10 treated equally) |
| **RRF** | **Rank-based, no normalization needed, robust to scale differences** |

**The k=60 parameter**: Dampens the effect of top-ranked items. With k=60:
- Rank 1 contributes 1/61 ≈ 0.0164
- Rank 5 contributes 1/65 ≈ 0.0154
- Rank 10 contributes 1/70 ≈ 0.0143

The difference between rank 1 and rank 10 is only ~15%, which prevents any single layer from dominating the final ranking.

## 3. Integration with Hermes

### 3.1 Injection Point

Eagle Eye uses the Hermes `pre_llm_call` plugin hook — zero core file modifications:

```python
# plugin.py
def _on_pre_llm_call(*, user_message: str = "", **_kwargs) -> dict | None:
    retriever = get_skill_retriever()
    result = retriever.retrieve_detailed(user_message)

    if result["layer"] == "L1":
        # Inject full SKILL.md content directly
        return {"context": f"## Auto-loaded Skill: {skill_name}\n{content}"}

    # L2-5: Inject lightweight hint
    return {"context": f"## Skill Retrieval Hint\n- {skill_names}"}
```

### 3.2 Prompt Injection Format

**L1 (hard trigger hit)**: Full skill content injected directly:
```
## Auto-loaded Skill: skill-name
[System note: This skill was automatically matched via hard trigger.]

[Full SKILL.md content here]
```

**L2-5 (pipeline hit)**: Lightweight hint, LLM decides:
```
## Skill Retrieval Hint
[System note: The following skills may be relevant to this query.
Use your judgment — load via skill_view() if useful, or ignore.]

- skill-name-1
- skill-name-2
```

### 3.3 Singleton Pattern

The retriever is a global singleton with thread-safe lazy initialization:

```python
_SINGLETON: "SkillRetriever | None" = None
_SINGLETON_LOCK = threading.Lock()

def get_skill_retriever():
    global _SINGLETON
    if _SINGLETON is None:
        with _SINGLETON_LOCK:
            if _SINGLETON is None:
                _SINGLETON = SkillRetriever()
    return _SINGLETON
```

First call blocks for ~10s (model loading + index building). Subsequent calls return instantly.

## 4. Failure Modes

| Failure | Impact | Mitigation |
|---------|--------|------------|
| `jieba` not installed | L2-L3 degrade | L1 still works, L4 still works |
| `sentence-transformers` not installed | L4 disabled | L1+L2+L3 still work |
| Model download fails | L4 disabled | Graceful fallback to L2+L3 |
| Synonym file missing | L3 disabled | L1+L2+L4 still work |
| All layers fail | No hints injected | LLM uses full skill list as before |
| `HERMES_DISABLE_SKILL_RETRIEVAL=1` | System disabled | Full skill list used |

**Degradation hierarchy**: L1 > L1+L2+L3 > L1+L2+L3+L4 > (no hints, full list)

## 5. Performance Characteristics

### 5.1 Latency Breakdown

| Component | First Call | Subsequent Calls |
|-----------|-----------|-----------------|
| L1 Hard Trigger | <1ms | <1ms |
| L2 FTS5 index build | ~500ms | 0 (cached) |
| L3 Synonym index build | ~200ms | 0 (cached) |
| L4 Model loading | ~10s | 0 (cached) |
| L4 Embedding computation | ~50ms | ~20ms |
| L5 RRF fusion | <1ms | <1ms |
| **Total** | **~11s** | **~20ms** |

### 5.2 Memory Usage

| Component | Memory |
|-----------|--------|
| FTS5 index (100 skills) | ~2MB |
| Synonym index (500 entries) | ~1MB |
| Embedding model | ~400MB |
| Embedding matrix (100×768) | ~0.3MB |
| **Total** | **~403MB** |

## 6. Confidence Gate

The retrieval system includes a **confidence gate** that prevents forced matches.
When the query doesn't match any skill well, the system returns an empty list,
and the LLM answers with general knowledge.

### Why a confidence gate?

Without it, the system always returns top-5 skills — even when the best match
is weak. This forces the LLM to load irrelevant skills, which can:
- Consume unnecessary context tokens
- Bias the LLM toward a skill's domain when general knowledge is better
- Produce worse answers than no skill at all

### Implementation

```python
_CONFIDENCE_THRESHOLD = 0.015  # top-1 must exceed this
```

### Design philosophy

**"Not matching" is itself a correct match result.**

Examples of correct non-matching:
- "What should I eat for dinner?" — lifestyle question
- "How's the weather?" — general knowledge
- "Python vs Java for web dev?" — career advice
- "What is the meaning of life?" — philosophy

These queries are best answered by the LLM's general knowledge, not by loading
a specific skill.

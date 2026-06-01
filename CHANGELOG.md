# Changelog

All notable changes to this project will be documented in this file.

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

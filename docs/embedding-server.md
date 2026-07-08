# Eagle Eye Embedding Server

## Endpoint

| Field | Value |
|-------|-------|
| URL | `http://localhost:3001/v1` |
| API | OpenAI-compatible (`/v1/embeddings`, `/v1/models`) |
| Auth | None (local) |

Set in `~/.hermes/.env`:
```
HERMES_EMBEDDING_BASE_URL=http://localhost:3001/v1
```

## Model

| Field | Value |
|-------|-------|
| Name | `v5-small-retrieval-Q8_0.gguf` |
| Architecture | jina-embeddings-v5 (small) |
| Parameters | 596,049,920 (~596M) |
| Embedding dim | 1024 |
| Context window | 8192 |
| Vocab size | 151,936 |
| File size | 633 MB |
| Quantization | Q8_0 (8-bit) |
| Format | GGUF |
| Server | llama.cpp (llamacpp) |

## Usage

The eagle-eye skill retriever calls `POST /v1/embeddings` with batch input:

```json
{
  "input": ["skill name, description", ...],
  "model": "default"
}
```

Response (OpenAI format):
```json
{
  "data": [
    {"index": 0, "embedding": [0.0068, 0.813, ...]},
    {"index": 1, "embedding": [0.012, 0.745, ...]}
  ]
}
```

## Configuration

Environment variables (read by `skill_retriever.py`):

| Variable | Default | Value |
|----------|---------|-------|
| `HERMES_EMBEDDING_BASE_URL` | `http://localhost:8080/v1` | `http://localhost:3001/v1` |
| `HERMES_EMBEDDING_MODEL` | `default` | `default` (llama.cpp ignores) |
| `HERMES_EMBEDDING_API_KEY` | (none) | (not needed) |
| `HERMES_EMBEDDING_BATCH_SIZE` | `16` | `16` |

## Cache

Embeddings are cached to `~/.hermes/.eagle_eye_emb_cache.npz`.

Cache key = SHA256 of skill names + descriptions + base_url + model_name. Invalidated when:
- Skills are added/removed/edited
- The embedding endpoint URL or model changes

First run: 236 skills × 1024 dims = 1.0 MB, ~71s via HTTP.
Cache hit: loads instantly from disk, no HTTP calls.

## Verification

```bash
# Check endpoint
curl http://localhost:3001/v1/models | python -m json.tool

# Test single embedding
curl -X POST http://localhost:3001/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"input": "test", "model": "default"}' | python -m json.tool | head -5

# Check logs after gateway restart
grep -i "embedding" ~/.hermes/logs/agent.log | tail -5
# Expected: "Embedding model loaded via HTTP: http://localhost:3001/v1, shape: (236, 1024)"
```

"""eagle-eye plugin — Intelligent skill routing.

Wires one behaviour:

* ``pre_llm_call`` hook — runs the skill retriever on each user query.

  **L1 hard trigger hit**: Injects skill content directly into context
  (capped at 4000 chars). No ``skill_view()`` round-trip needed. L1
  matches skip curator tracking — they're deterministic keyword matches,
  not judgment calls the curator needs to rank.

  **L2-5 pipeline hit**: Injects top skill names with descriptions as
  lightweight hints. The LLM decides whether to load them via
  ``skill_view()`` or ignore them.

  **No match**: Returns nothing. LLM uses general knowledge.

Design philosophy:
    L1 (hard triggers) = deterministic routing for obvious cases.
    L2-5 (retrieval) = hint provider, not decision maker.
    The LLM makes the final call on complex/ambiguous queries.

Disable via: ``HERMES_DISABLE_SKILL_RETRIEVAL=1``
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _on_pre_llm_call(*, user_message: str = "", **_kwargs) -> dict | None:
    """Run skill retrieval and inject result into user message."""
    if not user_message or not user_message.strip():
        return None

    # Skip system-injected messages — not real user queries
    _NOISE_PATTERNS = (
        "[ASYNC DELEGATION",
        "Review the conversation above",
        "[System",
        "[Balázs",  # Telegram sender prefix
    )
    stripped = user_message.strip()
    for pattern in _NOISE_PATTERNS:
        if stripped.startswith(pattern):
            return None

    # Strip [Replying to: "..."] prefix — the real query follows the ]
    if stripped.startswith("[Replying to:"):
        bracket_end = stripped.find('"]', 14)  # skip opening [Replying to: "
        if bracket_end != -1 and bracket_end + 2 < len(stripped):
            user_message = stripped[bracket_end + 2:].strip()
        else:
            return None  # Reply prefix with no actual message
    else:
        user_message = stripped

    if not user_message:
        return None

    try:
        from .skill_retriever import get_skill_retriever

        retriever = get_skill_retriever()
        result = retriever.retrieve_detailed(user_message)

        skills = result.get("skills", [])
        layer = result.get("layer", "none")

        if not skills:
            return None

        if layer == "L1":
            # ── L1: Direct content injection — no skill_view() round-trip ──
            #  Inject the skill content directly. L1 hard triggers are
            #  deterministic keyword matches, so we skip skill_usage tracking.
            skill_name = result.get("skill_name", skills[0])
            content = retriever.get_skill_content(skill_name) or ""

            # Paths may still be empty if L1 raced ahead of background init.
            # Fall back to a lightweight name hint instead of empty injection.
            if not content.strip():
                desc = retriever.get_skill_desc(skill_name)
                desc_bit = f" — {desc}" if desc else ""
                hint = (
                    f"## Skill Routing (Hard Trigger: {skill_name})\n"
                    f'[System: The skill "{skill_name}" was matched with 100% confidence'
                    f"{desc_bit}. Load via skill_view(\"{skill_name}\") "
                    f"— content not yet cached.]\n"
                )
                logger.info(
                    "Skill retriever L1: hint-only for %s (content not ready)",
                    skill_name,
                )
                return {"context": hint}

            # Cap injected content — full SKILL.md can be 100K+ chars
            _L1_CAP = 4000
            truncated = len(content) > _L1_CAP
            body = content[:_L1_CAP] if truncated else content

            truncation_note = ""
            if truncated:
                truncation_note = f' Truncated — call skill_view("{skill_name}") for full content.'

            hint = (
                f"## Skill Routing (Hard Trigger: {skill_name})\n"
                f'[System: The skill "{skill_name}" was matched with 100% confidence. '
                f"Its content is injected below.{truncation_note}]\n\n"
                f"---\n{body}\n---\n"
            )

            logger.info(
                "Skill retriever L1: direct injection of %s (%d chars%s)",
                skill_name, len(body),
                ", truncated" if truncated else "",
            )
            return {"context": hint}

        # ── L2-5: Inject hint with descriptions ──
        # When embedding layer is down, note degraded mode so the LLM
        # knows semantic matching is unavailable (FTS5+Synonyms only).
        degraded = not retriever.is_embedding_ready()
        header = "## Skill Retrieval Hint"
        if degraded:
            header += " (Degraded: semantic search unavailable)"

        lines = []
        for name in skills:
            desc = retriever.get_skill_desc(name)
            if desc:
                lines.append(f"- **{name}** — {desc}")
            else:
                lines.append(f"- **{name}**")

        hint = (
            header + "\n"
            "[System note: The following skills may be relevant to this query. "
            "Use your judgment — load via skill_view() if useful, "
            "or ignore and answer directly if none fit.]\n\n"
            + "\n".join(lines)
        )

        logger.info(
            "Skill retriever L2-5: %d skills hinted for query: %s%s",
            len(skills), user_message[:50],
            " [DEGRADED: embedding down]" if degraded else "",
        )
        return {"context": hint}

    except Exception as e:
        logger.warning("Skill retriever hook failed (non-fatal): %s", e)
        return None


def register(ctx) -> None:
    """Register the pre_llm_call hook with Hermes plugin system."""
    ctx.register_hook("pre_llm_call", _on_pre_llm_call)
    logger.info("eagle-eye plugin registered (pre_llm_call hook)")
    # Kick off singleton init in background; avoid noisy racey emb warnings.
    try:
        from .skill_retriever import get_skill_retriever
        retriever = get_skill_retriever()
        if retriever.is_embedding_ready():
            logger.info("eagle-eye: embedding layer operational (L4 active)")
        else:
            logger.info("eagle-eye: embedding init started (background)")
    except Exception as e:
        logger.warning("eagle-eye: could not start retriever: %s", e)

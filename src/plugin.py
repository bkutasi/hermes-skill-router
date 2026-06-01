"""eagle-eye plugin — Intelligent skill routing.

Wires one behaviour:

* ``pre_llm_call`` hook — runs the skill retriever on each user query.

  **L1 hard trigger hit**: Injects the full SKILL.md content directly into
  the user message. The LLM gets the skill immediately — no decision needed,
  no extra tool call.

  **L2-5 pipeline hit**: Injects top skill names as lightweight hints.
  The LLM decides whether to load them via skill_view() or ignore them.

  **No match**: Returns nothing. LLM uses general knowledge.

Design philosophy:
    L1 (hard triggers) = deterministic routing for obvious cases.
    L2-5 (retrieval) = hint provider, not decision maker.
    The LLM makes the final call on complex/ambiguous queries.

Disable via: ``HERMES_DISABLE_SKILL_RETRIEVAL=1``
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_DISABLE_ENV = "HERMES_DISABLE_SKILL_RETRIEVAL"

# Max skill content chars to inject (prevent token overflow)
_MAX_CONTENT_CHARS = 8000


def _on_pre_llm_call(*, user_message: str = "", **_kwargs) -> dict | None:
    """Run skill retrieval and inject result into user message."""
    if os.environ.get(_DISABLE_ENV, "").lower() in ("1", "true", "yes"):
        return None
    if not user_message or not user_message.strip():
        return None

    try:
        from agent.skill_retriever import get_skill_retriever

        retriever = get_skill_retriever()
        result = retriever.retrieve_detailed(user_message)

        skills = result.get("skills", [])
        layer = result.get("layer", "none")

        if not skills:
            return None

        if layer == "L1":
            # ── L1: Inject full SKILL.md content directly ──
            skill_name = result.get("skill_name", skills[0])
            content = retriever.get_skill_content(skill_name)

            if content:
                # Truncate if too long
                if len(content) > _MAX_CONTENT_CHARS:
                    content = content[:_MAX_CONTENT_CHARS] + "\n\n[... truncated ...]"

                injection = (
                    f"## Auto-loaded Skill: {skill_name}\n"
                    f"[System note: This skill was automatically matched "
                    f"via hard trigger. Use its instructions directly.]\n\n"
                    f"{content}"
                )

                logger.info(
                    "Skill retriever L1: injected %s (%d chars)",
                    skill_name, len(content),
                )
                return {"context": injection}

        # ── L2-5: Inject lightweight hint ──
        hint = (
            "## Skill Retrieval Hint\n"
            "[System note: The following skills may be relevant to this query. "
            "Use your judgment — load via skill_view() if useful, "
            "or ignore and answer directly if none fit.]\n\n"
            + "\n".join(f"- {name}" for name in skills)
        )

        logger.info(
            "Skill retriever L2-5: %d skills hinted for query: %s",
            len(skills), user_message[:50],
        )
        return {"context": hint}

    except Exception as e:
        logger.debug("Skill retriever hook failed (non-fatal): %s", e)
        return None


def register(ctx) -> None:
    """Register the pre_llm_call hook with Hermes plugin system."""
    ctx.register_hook("pre_llm_call", _on_pre_llm_call)
    logger.info("eagle-eye plugin registered (pre_llm_call hook)")

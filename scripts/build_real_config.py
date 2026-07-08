#!/usr/bin/env python3
"""Build real hard triggers + synonyms from skill names and descriptions.

Extracts keywords from skill names and descriptions to generate
high-quality L1 triggers and L3 synonyms — no TODOs.
"""

import re
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from generate_config import discover_skills, _extract_description

# Common stop words to filter out
STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "must", "shall", "can", "need", "to", "in",
    "on", "at", "by", "for", "of", "with", "from", "as", "into", "onto",
    "and", "or", "but", "not", "no", "if", "then", "else", "when", "where",
    "how", "what", "which", "who", "whom", "this", "that", "these", "those",
    "it", "its", "they", "them", "their", "we", "us", "our", "you", "your",
    "he", "him", "his", "she", "her", "via", "etc", "for", "per", "pro",
}

# Skills that should have hard triggers (high-confidence keyword → skill)
# Format: skill_name → list of trigger keywords
#
# This dict provides manually-curated, high-confidence trigger keywords for
# specific skills. These are merged with auto-generated triggers from skill
# names and descriptions. Add your own skills here — the keys must match
# the skill directory name under ~/.hermes/skills/.
MANUAL_TRIGGERS = {
    # ── Examples: replace these with your own skills ──
    "systematic-debugging": ["debug", "debugging", "root cause", "traceback"],
    "test-driven-development": ["TDD", "test-driven", "RED GREEN REFACTOR"],
    "github-workflows": ["github workflow", "github actions", "CI pipeline"],
    "github-code-review": ["code review", "PR review", "pull request review"],
    "github-issues": ["github issue", "create issue"],
    "github-auth": ["github auth", "gh auth", "github login"],
    "robust-bash-scripting": ["bash script", "shell script", "set -e"],
    "simplify-code": ["simplify code", "code cleanup", "refactor cleanup"],
    "adversarial-doc-review": ["adversarial review", "doc review"],
    "critical-expert-review": ["expert review", "critical review", "plan critique"],
    "wrangler": ["wrangler", "cloudflare workers", "CF Workers"],
    "tmux-configuration": ["tmux", "terminal multiplexer"],
    "linux-system-administration": ["kernel panic", "crash diagnosis", "system admin"],
    "deep-research-framework": ["deep research", "multi-source research"],
    "project-health-audit": ["project health", "audit project", "health audit"],
    "karpathy-guidelines": ["karpathy", "LLM coding guidelines"],
    "computer-use": ["computer use", "desktop automation", "click type"],
}


def extract_keywords_from_desc(desc: str) -> list[str]:
    """Extract meaningful keywords from a skill description."""
    if not desc:
        return []
    # Remove common punctuation
    text = re.sub(r"[^\w\s\-]", " ", desc.lower())
    words = text.split()
    keywords = [
        w for w in words
        if len(w) >= 3 and w not in STOP_WORDS and not w.isdigit()
    ]
    # Dedupe preserving order
    seen = set()
    result = []
    for w in keywords:
        if w not in seen:
            seen.add(w)
            result.append(w)
    return result[:8]  # Top 8 keywords


def extract_name_keywords(name: str) -> list[str]:
    """Extract keywords from skill name (e.g. 'systematic-debugging' → ['systematic', 'debugging'])."""
    parts = name.replace("-", " ").replace("_", " ").split()
    return [p.lower() for p in parts if len(p) >= 3]


def generate_triggers(skills: list[dict]) -> list[tuple[str, str]]:
    """Generate hard triggers from skill names, descriptions, and manual overrides."""
    triggers: list[tuple[str, str]] = []

    # 1. Manual triggers (highest quality)
    for skill_name, keywords in sorted(MANUAL_TRIGGERS.items()):
        for kw in keywords:
            triggers.append((kw, skill_name))

    # 2. Auto-generate from skill names (high confidence)
    #    Use the full hyphenated name as a trigger — individual words like
    #    "cron" or "status" are too generic and cause false positives.
    for skill in skills:
        name = skill["name"]
        # The full skill name itself is a trigger (e.g. "systematic-debugging")
        triggers.append((name, name))

    return triggers


def generate_synonyms(skills: list[dict]) -> dict[str, list[str]]:
    """Generate synonyms from skill descriptions and names."""
    synonyms: dict[str, list[str]] = {}

    for skill in skills:
        name = skill["name"]
        desc = skill["description"]
        syns: list[str] = []

        # From name parts
        name_parts = extract_name_keywords(name)
        syns.extend(name_parts)

        # From description keywords
        desc_keywords = extract_keywords_from_desc(desc)
        syns.extend(desc_keywords)

        # Add manual triggers as synonyms too
        if name in MANUAL_TRIGGERS:
            syns.extend(MANUAL_TRIGGERS[name])

        # Dedupe, filter, limit
        seen = set()
        unique = []
        for s in syns:
            s_lower = s.lower()
            if s_lower not in seen and s_lower not in STOP_WORDS and len(s_lower) >= 3:
                seen.add(s_lower)
                unique.append(s_lower)
        if unique:
            synonyms[name] = unique[:12]  # Max 12 synonyms per skill

    return synonyms


def write_triggers_py(triggers: list[tuple[str, str]], path: Path) -> None:
    lines = [
        "# Auto-generated hard triggers for Eagle Eye",
        f"# {len(triggers)} triggers covering your skill library",
        "# Review and adjust: remove false positives, add user-typed variants",
        "",
        "_HARD_TRIGGERS: list[tuple[str, str]] = [",
    ]
    for kw, skill in triggers:
        # Escape quotes in keyword
        safe_kw = kw.replace('"', '\\"')
        lines.append(f'    ("{safe_kw}", "{skill}"),')
    lines.append("]")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_synonyms_yaml(synonyms: dict[str, list[str]], path: Path) -> None:
    lines = [
        "# Auto-generated skill synonym dictionary for Eagle Eye",
        f"# {len(synonyms)} skills with synonyms",
        "# Review and refine: remove generic words, add natural language variants",
        "",
    ]
    for skill_name in sorted(synonyms.keys()):
        syns = synonyms[skill_name]
        lines.append(f"{skill_name}:")
        for syn in syns:
            safe_syn = syn.replace('"', '\\"')
            lines.append(f'  - "{safe_syn}"')
        lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    print("🦅 Eagle Eye Real Config Generator")
    print("=" * 40)
    print()

    skills = discover_skills()
    print(f"Found {len(skills)} skills")

    triggers = generate_triggers(skills)
    synonyms = generate_synonyms(skills)

    print(f"Generated {len(triggers)} hard triggers")
    print(f"Generated synonyms for {len(synonyms)} skills")

    out = Path(__file__).parent.parent / "src"
    write_triggers_py(triggers, out / "hard_triggers_generated.py")
    write_synonyms_yaml(synonyms, out / "skill_synonyms.yaml")

    print(f"\nWritten:")
    print(f"  src/hard_triggers_generated.py ({len(triggers)} triggers)")
    print(f"  src/skill_synonyms.yaml ({len(synonyms)} skills)")
    print(f"\nNext: the generated files are loaded automatically by skill_retriever.py")
    print(f"      Run 'bash scripts/install.sh' to install them to Hermes")


if __name__ == "__main__":
    main()

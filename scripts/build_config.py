#!/usr/bin/env python3
"""Build hard triggers + synonyms from the live Hermes skill tree.

One surface. Run after curator archive / new skills, then install.sh.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "must", "shall", "can", "need", "to", "in",
    "on", "at", "by", "for", "of", "with", "from", "as", "into", "onto",
    "and", "or", "but", "not", "no", "if", "then", "else", "when", "where",
    "how", "what", "which", "who", "whom", "this", "that", "these", "those",
    "it", "its", "they", "them", "their", "we", "us", "our", "you", "your",
    "he", "him", "his", "she", "her", "via", "etc", "per", "pro",
}

# High-confidence user-typed keywords. Keys must match skill dir names.
MANUAL_TRIGGERS = {
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
    "hermes-plugin-auditing": ["plugin audit", "hermes skill router", "eagle-eye", "audit plugin"],
}


def _extract_description(content: str) -> str:
    if not content.startswith("---"):
        return ""
    parts = content.split("---", 2)
    if len(parts) < 3:
        return ""
    for line in parts[1].split("\n"):
        if line.strip().startswith("description:"):
            return line.strip()[12:].strip().strip("\"'")
    return ""


def _discover_from_dir(base_dir: Path, skills: list[dict], seen: set[str]) -> None:
    """Keep in sync with skill_retriever._scan_skill_dir (skip dotdirs)."""
    for entry in sorted(base_dir.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        skill_md = entry / "SKILL.md"
        if skill_md.exists():
            name = entry.name
            if name not in seen:
                content = skill_md.read_text(encoding="utf-8")
                seen.add(name)
                skills.append({
                    "name": name,
                    "category": base_dir.name,
                    "description": _extract_description(content),
                    "path": str(skill_md),
                })
            # Nested packages under parent skill (keep in sync with skill_retriever)
            try:
                for sub in sorted(entry.iterdir()):
                    if (
                        sub.is_dir()
                        and not sub.name.startswith(".")
                        and (sub / "SKILL.md").exists()
                        and sub.name not in seen
                    ):
                        sm = sub / "SKILL.md"
                        content = sm.read_text(encoding="utf-8")
                        seen.add(sub.name)
                        skills.append({
                            "name": sub.name,
                            "category": entry.name,
                            "description": _extract_description(content),
                            "path": str(sm),
                        })
            except OSError:
                pass
        else:
            try:
                has_skill_md = any(
                    (sub / "SKILL.md").exists()
                    for sub in entry.iterdir()
                    if sub.is_dir() and not sub.name.startswith(".")
                )
            except OSError:
                has_skill_md = False
            if has_skill_md:
                _discover_from_dir(entry, skills, seen)


def discover_skills() -> list[dict]:
    hermes_home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
    skills: list[dict] = []
    seen: set[str] = set()
    for base_dir in (hermes_home / "skills", hermes_home / "hermes-agent" / "skills"):
        if base_dir.exists():
            _discover_from_dir(base_dir, skills, seen)
    return skills


def extract_keywords_from_desc(desc: str) -> list[str]:
    if not desc:
        return []
    text = re.sub(r"[^\w\s\-]", " ", desc.lower())
    keywords = [
        w for w in text.split()
        if len(w) >= 3 and w not in STOP_WORDS and not w.isdigit()
    ]
    seen: set[str] = set()
    result: list[str] = []
    for w in keywords:
        if w not in seen:
            seen.add(w)
            result.append(w)
    return result[:8]


def extract_name_keywords(name: str) -> list[str]:
    parts = name.replace("-", " ").replace("_", " ").split()
    return [p.lower() for p in parts if len(p) >= 3]


def generate_triggers(skills: list[dict]) -> list[tuple[str, str]]:
    triggers: list[tuple[str, str]] = []
    valid = {s["name"] for s in skills}
    for skill_name, keywords in sorted(MANUAL_TRIGGERS.items()):
        if skill_name not in valid:
            continue
        for kw in keywords:
            triggers.append((kw, skill_name))
    for skill in skills:
        name = skill["name"]
        # Auto name-trigger only when specific enough to avoid English false L1
        # (plan, maps, clip, …). Manual triggers cover short high-value skills.
        if len(name) >= 10 and "-" in name:
            triggers.append((name, name))
    return triggers


def generate_synonyms(skills: list[dict]) -> dict[str, list[str]]:
    synonyms: dict[str, list[str]] = {}
    for skill in skills:
        name = skill["name"]
        syns = extract_name_keywords(name) + extract_keywords_from_desc(skill["description"])
        if name in MANUAL_TRIGGERS:
            syns.extend(MANUAL_TRIGGERS[name])
        seen: set[str] = set()
        unique: list[str] = []
        for s in syns:
            s_lower = s.lower()
            if s_lower not in seen and s_lower not in STOP_WORDS and len(s_lower) >= 3:
                seen.add(s_lower)
                unique.append(s_lower)
        if unique:
            synonyms[name] = unique[:12]
    return synonyms


def write_triggers_py(triggers: list[tuple[str, str]], path: Path) -> None:
    lines = [
        "# Auto-generated hard triggers for Hermes Skill Router",
        f"# {len(triggers)} triggers — regenerate: python scripts/build_config.py",
        "",
        "_HARD_TRIGGERS: list[tuple[str, str]] = [",
    ]
    for kw, skill in triggers:
        safe_kw = kw.replace('"', '\\"')
        lines.append(f'    ("{safe_kw}", "{skill}"),')
    lines.append("]")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_synonyms_yaml(synonyms: dict[str, list[str]], path: Path) -> None:
    lines = [
        "# Auto-generated skill synonym dictionary for Hermes Skill Router",
        f"# {len(synonyms)} skills — regenerate: python scripts/build_config.py",
        "",
    ]
    for skill_name in sorted(synonyms.keys()):
        lines.append(f"{skill_name}:")
        for syn in synonyms[skill_name]:
            safe_syn = syn.replace('"', '\\"')
            lines.append(f'  - "{safe_syn}"')
        lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Hermes Skill Router triggers + synonyms")
    parser.add_argument("--scan-only", action="store_true", help="List skills only")
    args = parser.parse_args()

    skills = discover_skills()
    print(f"Found {len(skills)} skills")
    if args.scan_only:
        for s in sorted(skills, key=lambda x: x["name"]):
            print(f"  {s['name']}: {(s['description'] or '')[:60]}")
        return

    triggers = generate_triggers(skills)
    synonyms = generate_synonyms(skills)
    out = Path(__file__).resolve().parent.parent / "src"
    write_triggers_py(triggers, out / "hard_triggers_generated.py")
    write_synonyms_yaml(synonyms, out / "skill_synonyms.yaml")
    print(f"Generated {len(triggers)} hard triggers")
    print(f"Generated synonyms for {len(synonyms)} skills")
    print("Written: src/hard_triggers_generated.py, src/skill_synonyms.yaml")
    print("Next: bash scripts/install.sh && restart Hermes")


if __name__ == "__main__":
    main()

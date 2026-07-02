#!/usr/bin/env python3
"""Generate Eagle Eye config from your local Hermes skill library.

Scans ~/.hermes/skills/ and ~/.hermes/hermes-agent/skills/ to discover
your installed skills, then generates:
  1. hard_triggers.generated.py  — paste into src/skill_retriever.py
  2. skill_synonyms.generated.yaml — use as src/skill_synonyms.yaml

Usage:
    python scripts/generate_config.py                    # Interactive (uses LLM if available)
    python scripts/generate_config.py --scan-only        # Just list discovered skills
    python scripts/generate_config.py --output-dir ./out # Custom output directory
"""

from __future__ import annotations

import argparse
import os
import sys
import yaml
from pathlib import Path


def _discover_from_dir(base_dir: Path, skills: list[dict], seen: set[str]) -> None:
    """Recursively scan for SKILL.md files — handles flat and nested layouts."""
    for entry in sorted(base_dir.iterdir()):
        if not entry.is_dir():
            continue
        skill_md = entry / "SKILL.md"
        if skill_md.exists():
            name = entry.name
            if name in seen:
                continue
            content = skill_md.read_text(encoding="utf-8")
            desc = _extract_description(content)
            triggers = _extract_triggers(content)
            seen.add(name)
            skills.append({
                "name": name,
                "category": base_dir.name,
                "description": desc,
                "triggers": triggers,
                "path": str(skill_md),
            })
        else:
            # Could be a category directory — recurse
            has_skill_md = any(
                (sub / "SKILL.md").exists()
                for sub in entry.iterdir()
                if sub.is_dir()
            )
            if has_skill_md:
                _discover_from_dir(entry, skills, seen)


def discover_skills() -> list[dict]:
    """Scan Hermes skill directories and extract skill metadata."""
    hermes_home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
    search_dirs = [
        hermes_home / "skills",
        hermes_home / "hermes-agent" / "skills",
    ]

    skills = []
    seen = set()

    for base_dir in search_dirs:
        if not base_dir.exists():
            continue
        _discover_from_dir(base_dir, skills, seen)

    return skills


def _extract_description(content: str) -> str:
    """Extract description from SKILL.md frontmatter."""
    if not content.startswith("---"):
        return ""
    parts = content.split("---", 2)
    if len(parts) < 3:
        return ""
    for line in parts[1].split("\n"):
        if line.strip().startswith("description:"):
            return line.strip()[12:].strip().strip("\"'")
    return ""


def _extract_triggers(content: str) -> list[str]:
    """Extract trigger keywords from SKILL.md frontmatter."""
    if not content.startswith("---"):
        return []
    parts = content.split("---", 2)
    if len(parts) < 3:
        return []
    for line in parts[1].split("\n"):
        if line.strip().startswith("triggers:"):
            val = line.strip()[9:].strip()
            if val.startswith("["):
                try:
                    return eval(val)  # safe for list of strings
                except Exception:
                    pass
    return []


def generate_triggers_py(skills: list[dict]) -> str:
    """Generate hard triggers Python code."""
    lines = [
        "# Auto-generated hard triggers — paste into _HARD_TRIGGERS in skill_retriever.py",
        "# Generated from your local Hermes skill library",
        "# Review and adjust: remove false positives, add user-typed variants",
        "",
        "_HARD_TRIGGERS: list[tuple[str, str]] = [",
    ]

    # Group by category
    categories: dict[str, list[dict]] = {}
    for skill in skills:
        cat = skill["category"]
        categories.setdefault(cat, []).append(skill)

    for cat, cat_skills in sorted(categories.items()):
        lines.append(f"    # ── {cat} ──")
        for skill in cat_skills:
            name = skill["name"]
            desc_short = skill["description"][:60] if skill["description"] else ""
            if skill["triggers"]:
                for trigger in skill["triggers"]:
                    lines.append(f'    ("{trigger}", "{name}"),')
            else:
                # Generate placeholder from description keywords
                lines.append(f'    # TODO: Add triggers for {name} ({desc_short})')
                lines.append(f'    # ("your_keyword", "{name}"),')
        lines.append("")

    lines.append("]")
    return "\n".join(lines)


def generate_synonyms_yaml(skills: list[dict]) -> str:
    """Generate synonym dictionary YAML."""
    lines = [
        "# Auto-generated skill synonym dictionary",
        "# Generated from your local Hermes skill library",
        "# Review and refine: remove generic words, add natural language variants",
        "",
    ]

    # Group by category
    categories: dict[str, list[dict]] = {}
    for skill in skills:
        cat = skill["category"]
        categories.setdefault(cat, []).append(skill)

    for cat, cat_skills in sorted(categories.items()):
        lines.append(f"# {'=' * 50}")
        lines.append(f"# {cat}")
        lines.append(f"# {'=' * 50}")
        lines.append("")

        for skill in cat_skills:
            name = skill["name"]
            desc = skill["description"]
            lines.append(f"{name}:")
            if skill["triggers"]:
                for trigger in skill["triggers"]:
                    lines.append(f"  - {trigger}")
            if desc:
                # Extract key terms from description as seed synonyms
                lines.append(f"  # TODO: Add 5-15 natural language synonyms for this skill")
                lines.append(f"  # Description: {desc[:80]}")
            else:
                lines.append(f"  # TODO: Add synonyms — no description found")
            lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Generate Eagle Eye config from your Hermes skill library"
    )
    parser.add_argument(
        "--scan-only", action="store_true",
        help="Just list discovered skills, don't generate files"
    )
    parser.add_argument(
        "--output-dir", type=str, default="./generated",
        help="Output directory for generated files (default: ./generated)"
    )
    args = parser.parse_args()

    print("🦅 Eagle Eye Config Generator")
    print("=" * 40)
    print()

    # Discover skills
    print("Scanning Hermes skill directories...")
    skills = discover_skills()
    print(f"Found {len(skills)} skills")
    print()

    if args.scan_only:
        print("Discovered Skills:")
        print("-" * 60)
        categories: dict[str, list[dict]] = {}
        for skill in skills:
            categories.setdefault(skill["category"], []).append(skill)
        for cat, cat_skills in sorted(categories.items()):
            print(f"\n  [{cat}]")
            for skill in cat_skills:
                desc = skill["description"][:50] if skill["description"] else "(no description)"
                trigger_count = len(skill["triggers"])
                trigger_info = f" ({trigger_count} triggers)" if trigger_count else ""
                print(f"    - {skill['name']}{trigger_info}: {desc}")
        return

    # Generate files
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    triggers_path = output_dir / "hard_triggers.generated.py"
    synonyms_path = output_dir / "skill_synonyms.generated.yaml"

    triggers_content = generate_triggers_py(skills)
    synonyms_content = generate_synonyms_yaml(skills)

    triggers_path.write_text(triggers_content, encoding="utf-8")
    synonyms_path.write_text(synonyms_content, encoding="utf-8")

    print(f"Generated files:")
    print(f"  📄 {triggers_path}")
    print(f"  📄 {synonyms_path}")
    print()
    print("Next steps:")
    print("  1. Review the generated files")
    print("  2. Add user-typed trigger keywords (what users actually type)")
    print("  3. Add natural language synonyms (5-15 per skill)")
    print("  4. Copy to src/skill_retriever.py and src/skill_synonyms.yaml")
    print("  5. Run: bash scripts/install.sh")
    print()
    print("TIP: Use the prompts in PROMPTS.md with your LLM to generate")
    print("     higher-quality triggers and synonyms automatically.")


if __name__ == "__main__":
    main()

# LLM Prompts for Config Generation (English)

Use these prompts with any LLM (ChatGPT, Claude, Gemini, local models) to generate high-quality hard triggers and synonym dictionaries for your skill library.

## Workflow

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  1. Scan Skills  │ ──▶ │  2. Feed to LLM  │ ──▶ │  3. Review Output│
│                  │     │   with prompt    │     │                  │
│  generate_config │     │   from this file │     │  Remove generic  │
│  --scan-only     │     │                  │     │  Add colloquial  │
└──────────────────┘     └──────────────────┘     └──────────────────┘
                                                         │
                                                         ▼
                                                 ┌──────────────────┐
                                                 │  4. Deploy        │
                                                 │                  │
                                                 │  Paste into       │
                                                 │  skill_retriever  │
                                                 │  + synonyms.yaml  │
                                                 └──────────────────┘
```

---

## Prompt 1: Hard Triggers

```
You are helping configure an intelligent skill routing system for an AI assistant.

Given the following list of installed skills (name + description), generate hard trigger keywords for each skill.

Rules:
1. Each trigger should be what a user ACTUALLY types — natural language, not formal terms
2. Include both formal and colloquial variants (e.g., "debug" and "fix the bug")
3. Include bilingual variants if relevant (Chinese + English)
4. Avoid overly generic words that would match unrelated queries
5. Order: most specific triggers first
6. 3-8 triggers per skill is optimal
7. Triggers with fewer than 2 non-ASCII characters will skip fuzzy matching — prefer multi-character triggers

Output format (Python list of tuples):
```python
("trigger_keyword", "skill-name"),
```

Skills to configure:
[PASTE YOUR SKILL LIST HERE — name + description for each]
```

---

## Prompt 2: Synonym Dictionary

```
You are helping configure a skill retrieval system. The system uses a synonym dictionary to boost skill matching when user queries contain related terms.

Given the following skills, generate a synonym dictionary that maps natural language terms to each skill.

Rules:
1. Synonyms should be what users naturally type when they need this skill
2. Include colloquial/shortcut terms (e.g., "deck" for presentation skill)
3. Include both Chinese and English terms if your users are bilingual
4. 5-15 synonyms per skill
5. Avoid overly generic terms (e.g., "tool", "help", "use", "make")
6. Group related terms together
7. Include common misspellings or abbreviations if applicable

Output format (YAML):
```yaml
skill-name:
  - synonym1
  - synonym2
  - synonym3
```

Skills:
[PASTE YOUR SKILL LIST HERE]
```

---

## Prompt 3: Combined Generation (Recommended)

For a single-pass generation of both triggers and synonyms:

```
You are helping configure a 5-layer intelligent skill routing system for an AI assistant called Hermes Agent.

The system has two data files that need to be populated:

1. HARD TRIGGERS — Python list of (keyword, skill-name) tuples
   - Used for instant, deterministic matching
   - If user query contains the keyword, the skill loads immediately
   - Most specific triggers should come first (longest match wins)

2. SYNONYM DICTIONARY — YAML mapping of skill-name to keyword list
   - Used for fuzzy, probabilistic matching
   - Boosts skill score when user query contains synonym terms
   - 5-15 synonyms per skill

Given the following skills, generate BOTH files.

Rules for triggers:
- What users ACTUALLY type, not formal terminology
- Include formal + colloquial + bilingual variants
- Avoid generic words (e.g., "help", "use", "tool")
- 3-8 triggers per skill

Rules for synonyms:
- Natural language terms users would type when needing this skill
- Include abbreviations, shortcuts, and informal terms
- Avoid generic terms that would pollute matching
- Include both Chinese and English if bilingual

Output format:
```
=== HARD TRIGGERS ===
(trigger_keyword, "skill-name"),

=== SYNONYM DICTIONARY ===
skill-name:
  - synonym1
  - synonym2
```

Skills:
[PASTE YOUR SKILL LIST HERE — name + description for each]
```

---

## Advanced: Domain-Specific Tuning

If you have a specialized domain, add context to narrow the trigger/synonym space:

```
My primary domain is [YOUR DOMAIN].
My users are primarily [ROLE/PROFESSION].
Most queries will be about [TOPIC1], [TOPIC2], [TOPIC3].
The working language is [LANGUAGE] (with occasional [OTHER LANGUAGE] terms).

Please prioritize triggers and synonyms that are common in this domain.
De-prioritize generic terms that could match unrelated queries.
```

## Advanced: Negative Pattern Exclusion

To reduce false positives, define what should NOT match:

```
IMPORTANT: The following query types should NOT match any skill:
- General life questions (e.g., "what to eat", "weather today")
- Casual conversation (e.g., "how are you", "tell me a joke")
- Off-topic queries unrelated to my skill library

If a generated trigger could match any of these patterns, exclude it.
Err on the side of precision over recall — false negatives are acceptable,
false positives are not.
```

## Advanced: Iterative Refinement

After initial generation, use this follow-up prompt to refine:

```
Here is my current configuration after testing:

TRIGGERS: [paste current triggers]
SYNONYMS: [paste current synonyms]

During testing, I found these issues:
- False positive: "[query]" incorrectly matched "[skill]" — remove the trigger "[keyword]"
- False negative: "[query]" should have matched "[skill]" — add trigger "[keyword]"
- Low relevance: synonym "[term]" for skill "[skill]" is too generic — remove it

Please update the configuration to fix these issues while preserving everything else.
```

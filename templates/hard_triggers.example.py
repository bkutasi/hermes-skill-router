# Hard Triggers Template
# 
# Format: ("trigger_keyword", "skill-name")
# 
# Rules:
#   1. Order matters — first match wins. Put more specific triggers first.
#   2. Triggers should be what users ACTUALLY type, not formal terms.
#   3. CJK-only triggers get fuzzy matching (subsequence + regex).
#   4. Mixed CJK/ASCII triggers only match via exact substring.
#   5. Triggers with <2 CJK chars skip fuzzy matching (prevents false positives).
#
# CUSTOMIZATION: Run `python scripts/generate_config.py` to auto-generate.
# Then paste the output into src/skill_retriever.py's _HARD_TRIGGERS list.

# ── Example: High-confidence keyword → skill mappings ──

# ("debug", "systematic-debugging"),
# ("调试", "systematic-debugging"),
# ("代码审查", "zh-code-review"),
# ("做PPT", "powerpoint"),
# ("发邮件", "himalaya"),
# ("MCP", "mcp-builder-zh"),
# ("写计划", "writing-plans"),
# ("写文档", "zh-documentation"),

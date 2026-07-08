# Hard Triggers Template
# 
# Format: ("trigger_keyword", "skill-name")
# 
# Rules:
#   1. Longest trigger wins — when multiple triggers match, the most specific
#      (longest) one is selected. Ties broken by earliest position in query.
#   2. Tier 2 (subsequence) and Tier 3 (regex fuzzy) also collect all matches
#      and pick the longest trigger.
#   3. CJK-only triggers with 2+ CJK chars and no ASCII letters get fuzzy
#      matching (subsequence + regex).
#   4. Mixed CJK/ASCII triggers only match via exact substring.
#   5. Triggers with <2 CJK chars skip fuzzy matching (prevents false positives).
#
# CUSTOMIZATION: Run `python scripts/build_real_config.py` to auto-generate
# from your local skill library.

# ── Example: High-confidence keyword → skill mappings ──

# ("debug", "systematic-debugging"),
# ("调试", "systematic-debugging"),
# ("代码审查", "zh-code-review"),
# ("做PPT", "powerpoint"),
# ("发邮件", "himalaya"),
# ("MCP", "mcp-builder-zh"),
# ("写计划", "writing-plans"),
# ("写文档", "zh-documentation"),

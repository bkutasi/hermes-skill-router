#!/bin/bash
# Install eagle-eye as a Hermes plugin (zero core modification)
set -e

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
PLUGIN_DIR="$HERMES_HOME/plugins/eagle-eye"

SRC_DIR="$(dirname "$0")/../src"

echo "🦅 Installing Eagle Eye skill retriever..."

# 1. Create plugin directory and copy retrieval engine + config files
mkdir -p "$PLUGIN_DIR"
cp "$SRC_DIR/skill_retriever.py" "$PLUGIN_DIR/"

# 2. Copy generated config files if they exist (gitignored, user-specific)
if [ -f "$SRC_DIR/hard_triggers_generated.py" ]; then
    cp "$SRC_DIR/hard_triggers_generated.py" "$PLUGIN_DIR/"
    echo "  ✅ Copied hard_triggers_generated.py"
else
    echo "  ⚠️  hard_triggers_generated.py not found — run 'python scripts/build_config.py' first"
fi
if [ -f "$SRC_DIR/skill_synonyms.yaml" ]; then
    cp "$SRC_DIR/skill_synonyms.yaml" "$PLUGIN_DIR/"
    echo "  ✅ Copied skill_synonyms.yaml"
else
    echo "  ⚠️  skill_synonyms.yaml not found — run 'python scripts/build_config.py' first"
fi

# 3. Copy plugin entry point and manifest
cp "$SRC_DIR/plugin.py" "$PLUGIN_DIR/__init__.py"
cp "$SRC_DIR/plugin.yaml" "$PLUGIN_DIR/plugin.yaml"

# 4. Enable plugin (skip if already listed — avoid interactive hermes prompts)
if grep -q "eagle-eye" "$HERMES_HOME/config.yaml" 2>/dev/null; then
    echo "  ℹ️  Plugin already present in config.yaml"
elif hermes plugins enable eagle-eye </dev/null 2>/dev/null; then
    echo "  ✅ Plugin enabled via hermes plugins enable"
else
    # last resort: append only (no yaml.dump thrash)
    python3 -c "
from pathlib import Path
p = Path('$HERMES_HOME/config.yaml')
text = p.read_text(encoding='utf-8') if p.exists() else ''
if 'eagle-eye' not in text:
    if 'plugins:' not in text:
        text += '
plugins:
  enabled:
    - eagle-eye
'
    elif 'enabled:' in text:
        # insert under enabled list
        lines = text.splitlines(True)
        out = []
        for i, line in enumerate(lines):
            out.append(line)
            if line.strip() == 'enabled:' or line.rstrip().endswith('enabled:'):
                out.append('  - eagle-eye
' if not line.startswith(' ') else '    - eagle-eye
')
        p.write_text(''.join(out), encoding='utf-8')
    else:
        text += '
plugins:
  enabled:
    - eagle-eye
'
        p.write_text(text, encoding='utf-8')
print('enabled')
"
    echo "  ✅ Plugin enable attempted (append)"
fi

# 5. Install dependencies
echo ""
echo "Checking dependencies..."
VENV_PIP="$HERMES_HOME/hermes-agent/venv/bin/pip"
if [ -f "$VENV_PIP" ]; then
    "$VENV_PIP" install jieba numpy requests --quiet 2>/dev/null && \
        echo "  ✅ Dependencies installed" || \
        echo "  ⚠️  Some dependencies failed — check manually"
else
    echo "  ⚠️  Hermes venv not found at $VENV_PIP"
    echo "     Install manually: pip install jieba numpy requests"
fi

echo ""
echo "Installation complete! Restart Hermes to activate:"
echo "  hermes gateway restart"
echo ""
echo "To disable: set HERMES_DISABLE_SKILL_RETRIEVAL=1"
echo "To regenerate triggers/synonyms: python scripts/build_config.py"
echo "To list skills: python scripts/build_config.py --scan-only"

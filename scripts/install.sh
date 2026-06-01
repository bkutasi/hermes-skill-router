#!/bin/bash
# Install eagle-eye as a Hermes plugin (zero core modification)
set -e

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
PLUGIN_DIR="$HERMES_HOME/hermes-agent/plugins/eagle-eye"
AGENT_DIR="$HERMES_HOME/hermes-agent/agent"
SRC_DIR="$(dirname "$0")/../src"

echo "🦅 Installing Eagle Eye skill retriever..."

# 1. Copy retrieval engine + synonym dictionary to agent/
cp "$SRC_DIR/skill_retriever.py" "$AGENT_DIR/"
cp "$SRC_DIR/skill_synonyms.yaml" "$AGENT_DIR/"

# 2. Create plugin directory and copy plugin + manifest
mkdir -p "$PLUGIN_DIR"
cp "$SRC_DIR/plugin.py" "$PLUGIN_DIR/__init__.py"
cp "$SRC_DIR/plugin.yaml" "$PLUGIN_DIR/plugin.yaml"

# 3. Enable plugin in config (if not already)
CONFIG="$HERMES_HOME/config.yaml"
if ! grep -q "eagle-eye" "$CONFIG" 2>/dev/null; then
    python3 -c "
import yaml
with open('$CONFIG', 'r') as f:
    config = yaml.safe_load(f)
if 'plugins' not in config:
    config['plugins'] = {'enabled': []}
if 'enabled' not in config['plugins']:
    config['plugins']['enabled'] = []
if 'eagle-eye' not in config['plugins']['enabled']:
    config['plugins']['enabled'].append('eagle-eye')
with open('$CONFIG', 'w') as f:
    yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
"
    echo "  ✅ Plugin enabled in config.yaml"
else
    echo "  ℹ️  Plugin already enabled in config.yaml"
fi

# 4. Install dependencies
echo ""
echo "Checking dependencies..."
VENV_PIP="$HERMES_HOME/hermes-agent/venv/bin/pip"
if [ -f "$VENV_PIP" ]; then
    "$VENV_PIP" install jieba sentence-transformers --quiet 2>/dev/null && \
        echo "  ✅ Dependencies installed" || \
        echo "  ⚠️  Some dependencies failed — check manually"
else
    echo "  ⚠️  Hermes venv not found at $VENV_PIP"
    echo "     Install manually: pip install jieba sentence-transformers"
fi

echo ""
echo "Installation complete! Restart Hermes to activate:"
echo "  hermes gateway restart"
echo ""
echo "To disable: set HERMES_DISABLE_SKILL_RETRIEVAL=1"
echo "To customize: edit src/skill_retriever.py and src/skill_synonyms.yaml"
echo "To auto-generate: python scripts/generate_config.py"

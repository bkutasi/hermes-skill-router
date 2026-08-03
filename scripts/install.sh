#!/bin/bash
# Install hermes-skill-router as a Hermes plugin (zero core modification)
set -e

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
PLUGIN_NAME="hermes-skill-router"
LEGACY_PLUGIN_NAME="eagle-eye"
PLUGIN_DIR="$HERMES_HOME/plugins/$PLUGIN_NAME"
LEGACY_PLUGIN_DIR="$HERMES_HOME/plugins/$LEGACY_PLUGIN_NAME"
SRC_DIR="$(dirname "$0")/../src"

echo "Installing Hermes Skill Router..."

# Preserve warm caches while moving away from the legacy plugin identity.
for cache in emb_cache.npz text_index.npz; do
    old="$HERMES_HOME/.eagle_eye_$cache"
    new="$HERMES_HOME/.hermes_skill_router_$cache"
    if [ -f "$old" ] && [ ! -f "$new" ]; then
        cp "$old" "$new"
        echo "  Migrated cache: $(basename "$old")"
    fi
done

# 1. Create plugin directory and copy retrieval engine + config files
mkdir -p "$PLUGIN_DIR"
cp "$SRC_DIR/skill_retriever.py" "$PLUGIN_DIR/"

# 2. Copy generated config files if they exist (gitignored, user-specific)
if [ -f "$SRC_DIR/hard_triggers_generated.py" ]; then
    cp "$SRC_DIR/hard_triggers_generated.py" "$PLUGIN_DIR/"
    echo "  Copied hard_triggers_generated.py"
else
    echo "  WARNING: hard_triggers_generated.py not found — run 'python scripts/build_config.py' first"
fi
if [ -f "$SRC_DIR/skill_synonyms.yaml" ]; then
    cp "$SRC_DIR/skill_synonyms.yaml" "$PLUGIN_DIR/"
    echo "  Copied skill_synonyms.yaml"
else
    echo "  WARNING: skill_synonyms.yaml not found — run 'python scripts/build_config.py' first"
fi

# 3. Copy plugin entry point and manifest
cp "$SRC_DIR/plugin.py" "$PLUGIN_DIR/__init__.py"
cp "$SRC_DIR/plugin.yaml" "$PLUGIN_DIR/plugin.yaml"

# 4. Enable the new plugin identity.
if python3 -c "
import yaml
from pathlib import Path
p = Path('$HERMES_HOME/config.yaml')
c = yaml.safe_load(p.read_text()) if p.exists() else {}
en = (c or {}).get('plugins') or {}
enabled = en.get('enabled') or []
raise SystemExit(0 if '$PLUGIN_NAME' in enabled else 1)
" 2>/dev/null; then
    echo "  Plugin already in plugins.enabled"
elif hermes plugins enable "$PLUGIN_NAME" </dev/null 2>/dev/null; then
    echo "  Plugin enabled via hermes plugins enable"
else
    # Last resort: update only plugins.enabled.
    python3 -c "
import yaml
from pathlib import Path
p = Path('$HERMES_HOME/config.yaml')
c = yaml.safe_load(p.read_text()) if p.exists() else {}
if not isinstance(c, dict):
    c = {}
plugins = c.setdefault('plugins', {})
if not isinstance(plugins, dict):
    plugins = {}
    c['plugins'] = plugins
enabled = plugins.setdefault('enabled', [])
if not isinstance(enabled, list):
    enabled = []
    plugins['enabled'] = enabled
if '$PLUGIN_NAME' not in enabled:
    enabled.append('$PLUGIN_NAME')
    p.write_text(yaml.safe_dump(c, sort_keys=False, allow_unicode=True), encoding='utf-8')
print('enabled')
"
    echo "  Plugin enable attempted (append)"
fi

# 5. Retire the legacy identity after the replacement is safely installed.
if [ -d "$LEGACY_PLUGIN_DIR" ]; then
    hermes plugins disable eagle-eye </dev/null 2>/dev/null || true
    rm -rf "$LEGACY_PLUGIN_DIR"
    echo "  Migrated and removed legacy eagle-eye plugin"
fi

# 6. Install dependencies
printf '\nChecking dependencies...\n'
VENV_PIP="$HERMES_HOME/hermes-agent/venv/bin/pip"
if [ -f "$VENV_PIP" ]; then
    "$VENV_PIP" install jieba numpy requests --quiet 2>/dev/null && \
        echo "  Dependencies installed" || \
        echo "  WARNING: Some dependencies failed — check manually"
else
    echo "  WARNING: Hermes venv not found at $VENV_PIP"
    echo "     Install manually: pip install jieba numpy requests"
fi

printf '\nInstallation complete. Restart Hermes to activate:\n'
echo "  hermes gateway restart"
printf '\nTo disable: set HERMES_DISABLE_SKILL_RETRIEVAL=1\n'
echo "To regenerate triggers/synonyms: python scripts/build_config.py"
echo "To list skills: python scripts/build_config.py --scan-only"

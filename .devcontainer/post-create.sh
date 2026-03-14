#!/bin/bash
# Post-create script for browser-agent-test-fixture Codespace
# Runs once when the Codespace is created

set -e

echo "=== browser-agent-test-fixture Codespace Setup ==="

# Codespace secrets live in a base64-encoded file that only gets sourced for
# SSH sessions (via /etc/profile.d/codespaces.sh). post-create.sh runs before
# any SSH session, so we load them here using the same approach.
SECRETS_FILE="/workspaces/.codespaces/shared/.env-secrets"
if [ -z "$CODESPACE_GITHUB_TOKEN" ] && [ -f "$SECRETS_FILE" ]; then
    echo "  Loading codespace secrets from $SECRETS_FILE..."
    while read line; do
        key=$(echo $line | sed "s/=.*//")
        value=$(echo $line | sed "s/$key=//1")
        decodedValue=$(echo $value | base64 -d)
        export $key="$decodedValue"
    done < "$SECRETS_FILE"
fi

# 1. Install build dependencies first
echo "[1/5] Installing build dependencies..."
pip install hatchling setuptools wheel

# 2. Install reliable-ai library (before project deps that depend on it)
echo "[2/5] Installing reliable-ai..."

# Prefer CODESPACE_ secrets (user PAT with org access) over the auto-injected
# GITHUB_TOKEN (scoped only to the current repo, can't reach reliable-ai)
RELIABLE_AI_TOKEN="${CODESPACE_RELIABLE_AI_TOKEN:-${RELIABLE_AI_TOKEN}}"
GITHUB_TOKEN="${CODESPACE_GITHUB_TOKEN:-${GITHUB_TOKEN}}"

# Try multiple installation methods in order of preference:
# 1. PyPI (if published)
# 2. GitHub with token (for private repos)
# 3. GitHub public URL
# 4. Local path (for development)

RELIABLE_AI_REPO="https://github.com/dreamteam-ai-labs/reliable-ai.git"
# Default to public GitHub repo if not set
if [ -z "$RELIABLE_AI_REPO" ]; then
    RELIABLE_AI_REPO="https://github.com/dreamteam-ai-labs/reliable-ai.git"
fi

if pip install "reliable-ai[mcp]"; then
    echo "  Installed from PyPI"
elif [ -n "$RELIABLE_AI_TOKEN" ]; then
    # Use manual clone approach to skip submodules (avoids auth issues)
    echo "  Cloning from private GitHub (RELIABLE_AI_TOKEN)..."
    TEMP_DIR=$(mktemp -d)
    if git clone --depth=1 --no-recurse-submodules "https://${RELIABLE_AI_TOKEN}@${RELIABLE_AI_REPO#https://}" "$TEMP_DIR/reliable-ai"; then
        pip install "$TEMP_DIR/reliable-ai[mcp]"
        rm -rf "$TEMP_DIR"
        echo "  Installed via manual clone (RELIABLE_AI_TOKEN)"
    else
        rm -rf "$TEMP_DIR"
        echo "  [!] ERROR: Could not clone reliable-ai with RELIABLE_AI_TOKEN"
        exit 1
    fi
elif [ -n "$GITHUB_TOKEN" ]; then
    # Use manual clone approach to skip submodules (avoids auth issues)
    echo "  Cloning from private GitHub (GITHUB_TOKEN)..."
    TEMP_DIR=$(mktemp -d)
    if git clone --depth=1 --no-recurse-submodules "https://${GITHUB_TOKEN}@${RELIABLE_AI_REPO#https://}" "$TEMP_DIR/reliable-ai"; then
        pip install "$TEMP_DIR/reliable-ai[mcp]"
        rm -rf "$TEMP_DIR"
        echo "  Installed via manual clone (GITHUB_TOKEN)"
    else
        rm -rf "$TEMP_DIR"
        echo "  [!] ERROR: Could not clone reliable-ai with GITHUB_TOKEN"
        exit 1
    fi
elif pip install "reliable-ai[mcp] @ git+${RELIABLE_AI_REPO}"; then
    echo "  Installed from public GitHub"
elif [ -d "../reliable-ai" ]; then
    pip install -e "../reliable-ai[mcp]"
    echo "  Installed from local path (development mode)"
else
    echo "  [!] ERROR: Could not install reliable-ai"
    echo "  Check authentication tokens and repository access"
    echo "  Repository: ${RELIABLE_AI_REPO}"
    exit 1
fi

# 3. Install project dependencies (now reliable-ai is available)
echo "[3/5] Installing project dependencies..."
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
elif [ -f "pyproject.toml" ]; then
    pip install -e ".[dev]" 2>/dev/null || pip install -e .
fi

# 3.1. Sync deps into the pytest venv (Codespaces ships /usr/local/py-utils/venvs/pytest
#      with its own site-packages — if pytest is invoked from there it can't import our code)
PYTEST_VENV_PIP="/usr/local/py-utils/venvs/pytest/bin/pip"
if [ -x "$PYTEST_VENV_PIP" ]; then
    echo "  Syncing project deps into pytest venv..."
    $PYTEST_VENV_PIP install -e ".[dev]" 2>/dev/null || $PYTEST_VENV_PIP install -e . || true
fi

# 4. Install Claude Code CLI
echo "[4/5] Installing Claude Code..."
npm install -g @anthropic-ai/claude-code

# 5. Configure Claude Code
echo "[5/5] Configuring Claude Code..."
mkdir -p ~/.claude

# Copy project settings if they exist
if [ -f ".claude/settings.json" ]; then
    cp .claude/settings.json ~/.claude/settings.json
    echo "  Copied settings.json"
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "  1. Run 'claude' to authenticate with your Anthropic account"
echo "  2. Or set ANTHROPIC_API_KEY in Codespace secrets"
echo "  3. Say: 'Read CLAUDE.md and features.json, then start development'"
echo ""
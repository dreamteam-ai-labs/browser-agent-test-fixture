#!/bin/bash
# Post-create script for browser-agent-test-fixture Codespace
# Runs once when the Codespace is created
#
# IMPORTANT: Keep this FAST. The factory loop (factory-loop.js) handles
# reliable-ai installation and Claude Code verification defensively after
# provisioning. This script only needs to install project deps and Claude.
# Do NOT add slow steps here — they block codespace provisioning.

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

# 1. Install build dependencies
echo "[1/3] Installing build dependencies..."
pip install --quiet hatchling setuptools wheel

# 2. Install project dependencies
echo "[2/3] Installing project dependencies..."
if [ -f "requirements.txt" ]; then
    pip install --quiet -r requirements.txt
elif [ -f "pyproject.toml" ]; then
    pip install --quiet -e ".[dev]" 2>/dev/null || pip install --quiet -e .
fi

# 2.1. Sync deps into the pytest venv (Codespaces ships /usr/local/py-utils/venvs/pytest
#      with its own site-packages — if pytest is invoked from there it can't import our code)
PYTEST_VENV_PIP="/usr/local/py-utils/venvs/pytest/bin/pip"
if [ -x "$PYTEST_VENV_PIP" ]; then
    $PYTEST_VENV_PIP install --quiet -e ".[dev]" 2>/dev/null || $PYTEST_VENV_PIP install --quiet -e . || true
fi

# 3. Install Claude Code CLI
echo "[3/3] Installing Claude Code..."
npm install -g @anthropic-ai/claude-code

# Configure Claude Code
mkdir -p ~/.claude
if [ -f ".claude/settings.json" ]; then
    cp .claude/settings.json ~/.claude/settings.json
fi

echo "=== Setup Complete ==="
# NOTE: reliable-ai is installed by the factory loop runner (ensureReliableAiMcp
# or ensureAgentSdk) AFTER provisioning — always latest version from GitHub.
# Do NOT install it here — it adds 30-60s and the runner overwrites it anyway.
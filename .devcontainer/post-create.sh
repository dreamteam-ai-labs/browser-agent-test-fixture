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
#
# Always-load: source the file unconditionally so codespace secrets
# (CLAUDE_CODE_OAUTH_TOKEN, DREAMTEAM_SERVICE_API_KEY, etc.) are available to
# post-create even though no SSH session has run yet. An earlier
# `if [ -z "$CODESPACE_GITHUB_TOKEN" ]` guard could skip the load when the native
# auto-token raced ahead — always-load avoids that.
#
# NOTE (codespace cred-shed): this load NO LONGER exists to obtain a broad-scope
# GitHub PAT for cross-org pip clones. The cross-org private deps
# (dreamteam-service-auth, dreamteam-suggestions-mcp) are installed runner-side
# post-provision (see step 0.5 below), so the codespace holds no standing
# cross-org GitHub credential.
SECRETS_FILE="/workspaces/.codespaces/shared/.env-secrets"
if [ -f "$SECRETS_FILE" ]; then
    echo "  Loading codespace secrets from $SECRETS_FILE..."
    while read line; do
        key=$(echo $line | sed "s/=.*//")
        value=$(echo $line | sed "s/$key=//1")
        decodedValue=$(echo $value | base64 -d)
        export $key="$decodedValue"
    done < "$SECRETS_FILE"
fi

# 0. Ensure ~/.local/bin is in PATH for pip user installs (alembic, etc.)
#    Codespaces devcontainer image doesn't include this by default.
#    We write to .bashrc (interactive) and .profile (login shells / SSH).
if ! echo "$PATH" | grep -q "$HOME/.local/bin"; then
    export PATH="$HOME/.local/bin:$PATH"
fi
if ! grep -q '.local/bin' ~/.bashrc 2>/dev/null; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
fi
if ! grep -q '.local/bin' ~/.profile 2>/dev/null; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.profile
fi
# NOTE: Non-interactive SSH commands (bash -c "...") do NOT source .bashrc or
# .profile. Callers that invoke shell commands via SSH need to either use a
# login shell (bash -lc) or explicitly prepend PATH. The factory loop's
# run-claude.sh handles this.

# 0.5. (codespace cred-shed) NO git credentials are configured at create time —
#      and the codespace holds NO standing cross-org GitHub credential.
#      The factory-owned CROSS-ORG private deps (dreamteam-service-auth,
#      dreamteam-suggestions-mcp) are NOT in this project's main `dependencies`;
#      they live in the `services` / `buildtools` optional-dependency extras. So
#      the create-time `pip install -e ".[dev]"` below pulls only public packages
#      — no cross-org git clone, no token needed here.
#
#      Those private deps are installed INTO this codespace by the factory runner
#      post-provision (`pip install -e ".[dev,services,buildtools]"` with a
#      gateway-minted, contents:read, ~1h deps-token routed per-repo), AFTER
#      provisioning and BEFORE QA — so the suite can import them. The DEPLOYED
#      container gets the runtime `services` extra via the Dockerfile's BuildKit
#      GITHUB_TOKEN secret mount. This is why the prior broad-scope operator PAT
#      (loaded from $SECRETS_FILE) is shed: nothing here needs it.

# 1. Install build dependencies (skip if prebuilt image already has them)
echo "[1/3] Installing build dependencies..."
pip install --quiet hatchling setuptools wheel || true

# 2. Install project dependencies
# NOTE: stderr is left visible on purpose. Prior iterations used `2>/dev/null`,
# which converted distinguishable failure modes (git auth, hatchling direct-ref
# rejection, network errors) into an identical "package missing" symptom. Let
# the real error surface — the `||` fallback below is narrow (retry without
# dev extras only), not a catch-all silencer.
echo "[2/3] Installing project dependencies..."
if [ -f "requirements.txt" ]; then
    pip install --quiet -r requirements.txt
elif [ -f "pyproject.toml" ]; then
    if ! pip install --quiet -e ".[dev]"; then
        echo "  (dev extras unavailable — retrying without)"
        pip install --quiet -e .
    fi
fi

# 2.1. Sync deps into the pytest venv (Codespaces ships /usr/local/py-utils/venvs/pytest
#      with its own site-packages — if pytest is invoked from there it can't import our code)
PYTEST_VENV_PIP="/usr/local/py-utils/venvs/pytest/bin/pip"
if [ -x "$PYTEST_VENV_PIP" ]; then
    if ! $PYTEST_VENV_PIP install --quiet -e ".[dev]"; then
        echo "  (pytest venv: dev extras unavailable — retrying without)"
        $PYTEST_VENV_PIP install --quiet -e . || true
    fi
fi

# 3. Install Claude Code CLI (always install latest — non-negotiable)
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
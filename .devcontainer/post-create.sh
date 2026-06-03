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
# File-from-operator ALWAYS wins over the auto-injected env. GitHub injects
# CODESPACE_GITHUB_TOKEN scoped to the codespace's own repo only — pip
# git+https clones for cross-org private deps (dreamteam-service-auth,
# dreamteam-suggestions-mcp) hit 403 "Write access not granted" with that
# limited token even though it IS authenticated. The operator-uploaded
# user-level secret (broad-scope PAT) lives in $SECRETS_FILE and is the
# one we need. An earlier `if [ -z "$CODESPACE_GITHUB_TOKEN" ]` guard
# silently skipped the file load when the limited auto-token raced ahead,
# leaving pip with the wrong token. Always-load is the source-side fix
# pairing the factory's defensive R15/R16 SSH-context retry path.
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

# 0.5. Configure git credentials for private-repo pip deps. pyproject.toml may
#      pin factory-owned packages (dreamteam-service-auth,
#      dreamteam-suggestions-mcp, future services) as `git+https://...` URLs.
#      Without credentials, pip's clone step prompts for a password and the
#      install hangs (or the 2>/dev/null fallback below silently skips the
#      dep). The codespace always has CODESPACE_GITHUB_TOKEN; this maps it
#      onto github.com HTTPS URLs so pip can clone without prompting.
#      No-op if no private deps are declared — safe to run unconditionally.
TOKEN="${CODESPACE_GITHUB_TOKEN:-$GITHUB_TOKEN}"
if [ -n "$TOKEN" ]; then
    git config --global \
        url."https://x-access-token:${TOKEN}@github.com/".insteadOf \
        "https://github.com/"
    echo "  Configured git credentials for private pip deps"
fi

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

# 3. Install Claude Code CLI
# FORENSIC RIG PIN (2026-06-03): pinned to 2.1.160 — the directly-evidenced
# version the hang-era production codespace (-353) ran. The install path is
# image/prebuild-baked, NOT npm-latest-at-create, so unpinned could give 2.1.160
# OR a fresh-prebuild's latest; pinning reproduces the exact production binary.
# forensic-repro.js hard-asserts `claude --version` == 2.1.160 before any round.
# (Forensic fixture only — NOT a template change; production version policy is
# unaffected.)
echo "[3/3] Installing Claude Code (pinned 2.1.160 for forensic repro)..."
npm install -g @anthropic-ai/claude-code@2.1.160


# Configure Claude Code
mkdir -p ~/.claude
if [ -f ".claude/settings.json" ]; then
    cp .claude/settings.json ~/.claude/settings.json
fi

echo "=== Setup Complete ==="
# NOTE: reliable-ai is installed by the factory loop runner (ensureReliableAiMcp
# or ensureAgentSdk) AFTER provisioning — always latest version from GitHub.
# Do NOT install it here — it adds 30-60s and the runner overwrites it anyway.
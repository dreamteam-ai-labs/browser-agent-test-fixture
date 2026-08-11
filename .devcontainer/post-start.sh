#!/bin/bash
# Post-start script for browser-agent-test-fixture Codespace
# Runs each time the Codespace starts

echo "🔄 Starting browser-agent-test-fixture Codespace..."

# 0. Load codespace-injected secrets from the shared .env-secrets file.
#    GitHub Codespaces writes operator-uploaded user/org secrets here as
#    base64-encoded KEY=value lines. post-create.sh already loads this at
#    create time (see post-create.sh:28-37). post-start.sh ALSO needs to
#    load it because the SSH-spawned shells the factory loop uses (e.g.
#    codespace-runner.js bash -c "...") do NOT inherit the env from a
#    devcontainer login shell — they start with /etc/profile.d/codespaces.sh
#    only, which doesn't propagate CODESPACE_* secrets. Without this load,
#    the env-mapping loop in step 1 below sees nothing to map, and the
#    downstream ~/.dreamteam_env ends up with empty values (e.g.
#    CLAUDE_CODE_OAUTH_TOKEN=""), causing "Not logged in" failures at
#    Claude invocation time. Closes canary-6 (2026-05-28) Claude-auth bug.
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

# 1. Map all CODESPACE_ prefixed variables to unprefixed versions
#    Write to ~/.dreamteam_env (a dedicated file without shell guards)
#    so env vars are available in ALL shell types (interactive, SSH, CI)
echo ""
echo "📋 Mapping CODESPACE_ environment variables..."
: > ~/.dreamteam_env  # Truncate/create the env file

# 1.0. Capture GitHub's NATIVE injected token BEFORE the mapping loop below maps
#      CODESPACE_GITHUB_TOKEN (the fleet PAT) onto GITHUB_TOKEN. That mapping
#      CLOBBERS the native token, after which no shell trick can recover it while
#      CODESPACE_GITHUB_TOKEN is still present (Products-DB cred #4 codespace-cred-
#      shed, G1). The shed drops CODESPACE_GITHUB_TOKEN and relies on this native
#      token for in-codespace git writes, so the #1b probe must validate it
#      (repo-scoped push:true, NO admin:org/delete_repo/workflow classic scopes)
#      WHILE the fleet secret is still present. Step 0 above only sets CODESPACE_-
#      prefixed keys, so $GITHUB_TOKEN is still native here. Persist so the probe's
#      SSH/login shell reads it via ~/.dreamteam_env.
if [ -n "$GITHUB_TOKEN" ]; then
    export NATIVE_GITHUB_TOKEN="$GITHUB_TOKEN"
    echo "export NATIVE_GITHUB_TOKEN='$GITHUB_TOKEN'" >> ~/.dreamteam_env
    echo "  ✅ Captured NATIVE_GITHUB_TOKEN before CODESPACE_ mapping (native, pre-clobber)"
else
    echo "  ⚠️  GITHUB_TOKEN empty at capture point — NATIVE_GITHUB_TOKEN not set (G1: native token not visible to post-start; probe will report absent)"
fi

for var in $(env | grep '^CODESPACE_' | cut -d= -f1); do
    # Get the name without CODESPACE_ prefix
    unprefixed_name="${var#CODESPACE_}"
    # Export the unprefixed version
    export "$unprefixed_name"="${!var}"
    echo "  ✅ Mapped $var → $unprefixed_name"
    # Persist to dedicated env file
    echo "export $unprefixed_name='${!var}'" >> ~/.dreamteam_env
done

# 1.1. Preserve CODESPACE_NAME for scripts that need the display name
#      (e.g. qa-smoke-test.py constructs https://{CODESPACE_NAME}-{port}.app.github.dev)
#      The built-in CODESPACE_NAME is the container hostname, not the display name.
#      The CODESPACE_ mapping above gives us NAME=<display-name>, so re-export it.
if [ -n "$NAME" ]; then
    export CODESPACE_NAME="$NAME"
    echo "export CODESPACE_NAME='$NAME'" >> ~/.dreamteam_env
    echo "  ✅ CODESPACE_NAME preserved as $NAME"
fi

# Direct GCP/Firebase IdP credential plumbing removed (v0.8.18) — end-user
# auth goes through the DreamTeam auth facade (auth_provider: dreamteam_auth).
# GCP credentials live on the auth service, never on generated products.

# 2.5. Source env vars from ~/.profile and ~/.bashrc so ALL shell types get them
#    ~/.profile: sourced by login shells (SSH, CI)
#    ~/.bashrc: sourced by interactive shells (VS Code terminal)
#    The guard in ~/.bashrc ("if not running interactively, return") blocks
#    appended exports, so we insert the source line BEFORE it via sed.
if ! grep -q 'dreamteam_env' ~/.profile 2>/dev/null; then
    echo '[ -f ~/.dreamteam_env ] && . ~/.dreamteam_env' >> ~/.profile
fi
if ! grep -q 'dreamteam_env' ~/.bashrc 2>/dev/null; then
    sed -i '1i [ -f ~/.dreamteam_env ] && . ~/.dreamteam_env' ~/.bashrc
fi

# 3. Check for API keys
echo ""
echo "🔍 Checking API keys..."

check_secret() {
    local name=$1
    local var_value="${!name}"
    if [ -n "$var_value" ]; then
        # Show masked value for verification
        local masked="${var_value:0:8}..."
        echo "  ✅ $name is set ($masked)"
    else
        echo "  ⚠️  $name not set"
    fi
}

check_secret "CLAUDE_CODE_OAUTH_TOKEN"
check_secret "LINEAR_API_KEY"
# STRIPE_* checks removed (cred-shed 2026-06): Stripe keys are product-runtime
# Coolify references, not present in the authoring codespace; live Stripe is
# validated post-deploy by the payment-harness.

# 4. Test connections
echo ""
echo "🔍 Testing service connections..."

# Test Linear API
if [ ! -z "$LINEAR_API_KEY" ]; then
    RESPONSE=$(curl -s -X POST https://api.linear.app/graphql \
        -H "Authorization: $LINEAR_API_KEY" \
        -H "Content-Type: application/json" \
        -d '{"query":"{ viewer { id email } }"}' 2>/dev/null)

    if echo "$RESPONSE" | grep -q "email"; then
        echo "  ✅ Linear API connection successful"
    else
        echo "  ⚠️  Linear API connection failed"
    fi
else
    echo "  ℹ️  Linear API key not configured"
fi

# 5. Verify MCP servers configured
echo ""
echo "🔧 Verifying MCP servers..."
if [ -f ".mcp.json" ]; then
    echo "  ✅ .mcp.json found — MCP servers configured (reliable-ai, filesystem, code-search)"
else
    echo "  ⚠️  .mcp.json not found — MCP servers may not be available"
fi

# Ensure Claude CLI is available
if ! command -v claude &> /dev/null; then
    echo "📦 Installing Claude Code CLI..."
    npm install -g @anthropic-ai/claude-code || echo "⚠️  Could not install Claude CLI"
fi

# 6. Show project status
echo ""
echo "📊 Project status..."

if [ -f "features.json" ]; then
    python -c "
import json
with open('features.json') as f:
    data = json.load(f)
    features = data.get('features', [])
    completed = sum(1 for f in features if f.get('status') == 'completed')
    pending = sum(1 for f in features if f.get('status') == 'pending')
    print(f'  Features: {completed} completed, {pending} pending')
    for f in features:
        if f.get('status') == 'pending':
            print(f'  Next: {f.get(\"name\", \"Unknown\")}')
            break
" 2>/dev/null || echo "  ℹ️  Could not read features.json"
fi

echo ""
echo "✨ Codespace ready for development!"
echo ""
echo "To begin:"
echo "  1. Click on Claude Code in the sidebar"
echo "  2. Start a new conversation"
echo "  3. Say: 'Read CLAUDE.md and features.json, then start development'"
echo ""
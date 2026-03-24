#!/bin/bash
# Post-start script for browser-agent-test-fixture Codespace
# Runs each time the Codespace starts

echo "🔄 Starting browser-agent-test-fixture Codespace..."

# 1. Map all CODESPACE_ prefixed variables to unprefixed versions
#    Write to ~/.dreamteam_env (a dedicated file without shell guards)
#    so env vars are available in ALL shell types (interactive, SSH, CI)
echo ""
echo "📋 Mapping CODESPACE_ environment variables..."
: > ~/.dreamteam_env  # Truncate/create the env file
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

# 1.5. Set dynamic variables generated during project creation
echo ""
echo "🎯 Setting dynamic project variables..."
export GCPIP_TENANT_ID=""
echo "  ✅ Set GCPIP_TENANT_ID="
echo "export GCPIP_TENANT_ID=''" >> ~/.dreamteam_env

# 2. Handle Google Application Credentials
echo ""
echo "📝 Setting up Google Application Credentials..."
if [ ! -z "${GOOGLE_APPLICATION_CREDENTIALS_JSON}" ]; then
    # Write the JSON content to a file (use printf to handle special characters)
    printf '%s' "${GOOGLE_APPLICATION_CREDENTIALS_JSON}" > /tmp/gcp-service-account.json
    export GOOGLE_APPLICATION_CREDENTIALS="/tmp/gcp-service-account.json"
    echo "  ✅ Google credentials configured at /tmp/gcp-service-account.json"
    # Persist to dedicated env file
    echo "export GOOGLE_APPLICATION_CREDENTIALS='/tmp/gcp-service-account.json'" >> ~/.dreamteam_env
    # Verify the file was created and has content
    if [ -s /tmp/gcp-service-account.json ]; then
        echo "  ✅ File size: $(wc -c < /tmp/gcp-service-account.json) bytes"
    else
        echo "  ⚠️  Warning: File appears to be empty"
    fi
else
    echo "  ℹ️  GOOGLE_APPLICATION_CREDENTIALS_JSON not set - GCP auth will not work"
fi

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
check_secret "ANTHROPIC_API_KEY"
check_secret "GCP_API_KEY"
check_secret "GCPIP_TENANT_ID"
check_secret "LINEAR_API_KEY"
check_secret "STRIPE_SECRET_KEY"
check_secret "STRIPE_PUBLISHABLE_KEY"

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
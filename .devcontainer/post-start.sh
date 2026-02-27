#!/bin/bash
# Post-start script — runs each time the Codespace starts
echo "Starting QA Browser Test Harness..."

# 0. Map CODESPACE_ prefixed secrets to unprefixed versions
echo "[0/3] Mapping CODESPACE_ environment variables..."
for var in $(env | grep '^CODESPACE_' | cut -d= -f1); do
    unprefixed="${var#CODESPACE_}"
    export "$unprefixed"="${!var}"
    echo "  Mapped $var -> $unprefixed"
done
# Persist so login shells (SSH, Claude) get them too
env | grep '^CODESPACE_' | while IFS='=' read -r key val; do
    unprefixed="${key#CODESPACE_}"
    echo "export $unprefixed='$val'"
done > ~/.dreamteam_env
if ! grep -q 'dreamteam_env' ~/.bashrc 2>/dev/null; then
    sed -i '1i [ -f ~/.dreamteam_env ] && . ~/.dreamteam_env' ~/.bashrc
fi
if ! grep -q 'dreamteam_env' ~/.profile 2>/dev/null; then
    echo '[ -f ~/.dreamteam_env ] && . ~/.dreamteam_env' >> ~/.profile
fi

# Find workspace dir (may be /workspaces/browser-agent-test-fixture or /workspaces/)
WORKDIR="/workspaces/browser-agent-test-fixture"
if [ ! -f "$WORKDIR/requirements.txt" ]; then
    WORKDIR="/workspaces"
fi

# 1. Start backend (in background)
echo "[1/3] Starting backend on port 8000..."
pkill -f uvicorn 2>/dev/null || true
sleep 1
cd "$WORKDIR"
PYTHONPATH=src nohup python3 -m uvicorn fixture.main:app --host 0.0.0.0 --port 8000 > /tmp/backend.log 2>&1 &
sleep 3

# 2. Start frontend dev server (in background)
echo "[2/3] Starting frontend on port 3000..."
pkill -f 'next dev' 2>/dev/null || true
sleep 1
cd "$WORKDIR/frontend"
nohup npx next dev -p 3000 > /tmp/frontend.log 2>&1 &
cd "$WORKDIR"
sleep 3

# 3. Health check
echo "[3/3] Health check..."
curl -s http://localhost:8000/api/health || echo "Backend not ready yet"

echo ""
echo "QA Browser Test Harness ready!"
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:3000"

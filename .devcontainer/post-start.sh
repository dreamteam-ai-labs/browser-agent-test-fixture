#!/bin/bash
# Post-start script — runs each time the Codespace starts
echo "Starting QA Browser Test Harness..."

# 1. Start backend (in background)
echo "[1/2] Starting backend on port 8000..."
pkill -f uvicorn 2>/dev/null; sleep 1
cd /workspaces/browser-agent-test-fixture
PYTHONPATH=src python3 -m uvicorn fixture.main:app --host 0.0.0.0 --port 8000 &
sleep 3

# 2. Start frontend dev server (in background)
echo "[2/2] Starting frontend on port 3000..."
pkill -f 'next dev' 2>/dev/null; sleep 1
cd /workspaces/browser-agent-test-fixture/frontend && npx next dev -p 3000 &
cd /workspaces/browser-agent-test-fixture
sleep 3

# 3. Health check
echo ""
echo "Checking backend health..."
curl -s http://localhost:8000/api/health || echo "Backend not ready yet — will start momentarily"

echo ""
echo "QA Browser Test Harness ready!"
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:3000"

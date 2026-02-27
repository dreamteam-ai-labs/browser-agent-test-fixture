#!/bin/bash
# Post-create script — runs once when the Codespace is created
set -e

echo "=== QA Browser Test Harness — Codespace Setup ==="

# 1. Install backend dependencies
echo "[1/3] Installing backend dependencies..."
pip install -r requirements.txt

# 2. Install frontend dependencies
echo "[2/3] Installing frontend dependencies..."
cd frontend && npm install && cd ..

# 3. Install Claude Code CLI
echo "[3/3] Installing Claude Code..."
npm install -g @anthropic-ai/claude-code

echo ""
echo "=== Setup Complete ==="

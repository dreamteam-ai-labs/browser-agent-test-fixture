#!/bin/bash
set -e

# Decode base64 GCP credentials if present (multiline JSON breaks Docker ARG)
if [ -n "$GOOGLE_APPLICATION_CREDENTIALS_JSON_B64" ]; then
  export GOOGLE_APPLICATION_CREDENTIALS_JSON=$(echo "$GOOGLE_APPLICATION_CREDENTIALS_JSON_B64" | base64 -d)
  echo "GCP credentials decoded from base64"
fi

# SERVICE env var controls what this container runs:
#   backend  — FastAPI on port 8000
#   frontend — Next.js on port 3000
#   both     — both (default, for codespace dev)
SERVICE="${SERVICE:-both}"

if [ "$SERVICE" = "backend" ] || [ "$SERVICE" = "both" ]; then
  # Run Alembic migrations
  if [ -n "$DATABASE_URL" ]; then
    echo "Running database migrations..."
    alembic upgrade head 2>/dev/null || echo "Migrations skipped"
  fi

  echo "Starting backend on port 8000..."
  if [ "$SERVICE" = "backend" ]; then
    # Backend only — run in foreground
    exec uvicorn src.fixture.main:app --host 0.0.0.0 --port 8000
  else
    # Both — run in background
    uvicorn src.fixture.main:app --host 0.0.0.0 --port 8000 &
    BACKEND_PID=$!
  fi
fi

if [ "$SERVICE" = "frontend" ] || [ "$SERVICE" = "both" ]; then
  echo "Starting frontend on port 3000..."
  if [ "$SERVICE" = "frontend" ]; then
    # Frontend only — run in foreground
    cd frontend && exec npx next start -p 3000
  else
    # Both — run in background
    cd frontend && NODE_ENV=production npx next start -p 3000 &
    FRONTEND_PID=$!
    cd ..
  fi
fi

# If running both, wait for either to exit
if [ "$SERVICE" = "both" ]; then
  wait -n $BACKEND_PID $FRONTEND_PID
  kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
  exit 1
fi

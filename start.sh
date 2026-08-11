#!/bin/bash
set -e

# SERVICE env var controls what this container runs:
#   backend  — FastAPI on port 8000
#   frontend — Next.js on port 3000
#   both     — both (default, for codespace dev)
SERVICE="${SERVICE:-both}"

if [ "$SERVICE" = "backend" ] || [ "$SERVICE" = "both" ]; then
  # Stateless product (use_postgres:false) — JSON persistence, no schema/alembic.
  # database.py is the placeholder variant, so run NO DB boot — see the
  # use_postgres gate rationale in the infrastructure-service branch below.
  echo "Starting backend on port 8000..."
  if [ "$SERVICE" = "backend" ]; then
    # Backend only — run in foreground
    exec uvicorn fixture.main:app --host 0.0.0.0 --port 8000
  else
    # Both — run in background
    uvicorn fixture.main:app --host 0.0.0.0 --port 8000 &
    BACKEND_PID=$!
  fi
fi

if [ "$SERVICE" = "frontend" ] || [ "$SERVICE" = "both" ]; then
  echo "Starting frontend on port 3000..."
  # HOSTNAME=0.0.0.0 required — standalone server uses process.env.HOSTNAME for binding.
  # Without it, Docker sets HOSTNAME to container ID and Traefik gets 502.
  export HOSTNAME=0.0.0.0
  if [ "$SERVICE" = "frontend" ]; then
    # Frontend only — run in foreground
    cd frontend && PORT=3000 exec node server.js
  else
    # Both — run in background
    cd frontend && PORT=3000 NODE_ENV=production node server.js &
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

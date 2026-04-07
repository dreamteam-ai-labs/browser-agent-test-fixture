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
  # Fresh deploy: clean schema before starting (set by factory loop for new products)
  if [ "$FRESH_DEPLOY" = "true" ] && [ -n "$DATABASE_URL" ]; then
    echo "Fresh deploy: resetting database schema..."
    python3 -c "
from fixture.database import create_tables, Base, get_engine
engine = get_engine()
Base.metadata.drop_all(bind=engine)
create_tables()
print('Schema reset complete')
" || echo "ERROR: Schema reset failed"
  fi

  # Run Alembic migrations
  if [ -n "$DATABASE_URL" ]; then
    echo "Running database migrations..."
    alembic upgrade head 2>/dev/null || echo "Migrations skipped"
  fi

  # Ensure all tables exist (idempotent — skips existing, creates missing)
  if [ -n "$DATABASE_URL" ]; then
    python3 -c "from fixture.database import create_tables; create_tables()" \
      || echo "ERROR: Table creation failed"
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

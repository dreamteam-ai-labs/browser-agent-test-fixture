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
  # Fresh deploy: drop the WHOLE schema (incl. alembic_version stamp) and
  # re-create it empty, so the subsequent `alembic upgrade head` re-applies
  # all migrations from scratch. drop_tables() alone is INSUFFICIENT —
  # Base.metadata.drop_all() drops ORM tables but leaves alembic_version
  # stamped at HEAD; the next upgrade then no-ops (current==head) and the
  # ORM tables stay dropped. Canary-9 (2026-05-28) caught this class — the
  # codespace+live shared-schema masking made it silent for months.
  if [ "$FRESH_DEPLOY" = "true" ] && [ -n "$DATABASE_URL" ]; then
    echo "Fresh deploy: dropping schema..."
    python3 -c "
from fixture.database import drop_schema_cascade
drop_schema_cascade()
print('Schema dropped + recreated')
" || exit 1
  fi

  # Run database migrations. Alembic is the only schema source — no
  # create_tables fallback. If alembic isn't present or fails, exit non-zero
  # so the orchestrator catches the broken deploy at boot rather than serving
  # requests against a missing/stale schema.
  if [ -n "$DATABASE_URL" ]; then
    # Ensure SERVICE_SCHEMA exists before alembic — alembic targets a
    # schema-qualified Base.metadata, so the schema must exist first.
    # Idempotent (CREATE SCHEMA IF NOT EXISTS).
    python3 -c "from fixture.database import ensure_schema_exists; ensure_schema_exists()" \
      || exit 1

    if [ -f "alembic.ini" ]; then
      # Self-heal an out-of-band schema before upgrading. If the schema already
      # holds application tables but carries NO alembic_version stamp (a door-2
      # pre-deploy reset or an interrupted provision created the tables without
      # stamping), `alembic upgrade head` would re-issue rev-1 CREATE TABLE →
      # DuplicateTable → exit 1 → Docker restart → crash-loop (canary-9 #60 /
      # BUG2b). Stamp head to ADOPT the existing tables instead of re-creating
      # them. Data-safe: a healthy deploy is always stamped so this is a no-op,
      # and FRESH_DEPLOY's drop_schema_cascade leaves an empty schema so it's
      # skipped on fresh. See database.py::schema_needs_baseline_stamp.
      NEEDS_STAMP=$(python3 -c "from fixture.database import schema_needs_baseline_stamp; print('yes' if schema_needs_baseline_stamp() else 'no')") || exit 1
      if [ "$NEEDS_STAMP" = "yes" ]; then
        echo "Out-of-band schema detected (tables present, no alembic stamp) — stamping head to adopt it"
        alembic stamp head || exit 1
      fi
      echo "Running Alembic migrations..."
      alembic upgrade head || exit 1
    else
      echo "ERROR: alembic.ini missing — no migration source available"
      exit 1
    fi
  fi

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

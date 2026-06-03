# syntax=docker/dockerfile:1
# Multi-stage Dockerfile for browser-agent-test-fixture
# Stage 1: Build frontend
# Stage 2: Run backend + serve frontend

# --- Stage 1: Build Next.js frontend ---
FROM node:20-slim AS frontend-build

WORKDIR /app/frontend
COPY frontend/package*.json ./
# Force dev deps for this command only — Coolify injects NODE_ENV=production
# which skips typescript, tailwindcss, etc. Using inline env so it doesn't
# leak into npm run build (Next.js 16 fails with NODE_ENV=development).
RUN NODE_ENV=development npm install
COPY frontend/ ./
# NEXT_PUBLIC_* vars are baked into the JS bundle at build time.
# Coolify sets this as a build-time env var via is_build_time=true.
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

# --- Stage 2: Python backend + static frontend ---
FROM python:3.12-slim

WORKDIR /app

# Install Node.js (Next.js production server) + git (pip clones private deps)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Copy everything needed for pip install (README.md optional via wildcard)
COPY pyproject.toml README* ./
COPY src/ ./src/
# Install private factory-owned pip deps via BuildKit secret mount. The token
# (dreamteam-service-auth, dreamteam-suggestions-mcp, etc. — declared as
# `git+https://...` URLs in pyproject.toml) is read from tmpfs at
# /run/secrets/GITHUB_TOKEN and never appears in build args, `docker history`,
# layer metadata, or build logs (journald). If the secret is absent or empty,
# the build still works for services without private deps. Wired through by
# the factory's Coolify deploy step (codespace-runner.deployCoolify) as
# `--secret id=GITHUB_TOKEN,env=GITHUB_TOKEN`.
RUN --mount=type=secret,id=GITHUB_TOKEN \
    if [ -s /run/secrets/GITHUB_TOKEN ]; then \
        TOKEN="$(cat /run/secrets/GITHUB_TOKEN)" && \
        git config --global \
            url."https://x-access-token:${TOKEN}@github.com/".insteadOf \
            "https://github.com/" && \
        pip install --no-cache-dir . && \
        git config --global --unset url."https://x-access-token:${TOKEN}@github.com/".insteadOf; \
    else \
        pip install --no-cache-dir .; \
    fi

# Validate all imports resolve — fail the build if deps are missing.
RUN python -c "from fixture.main import app; print('Import validation passed')"

# Copy alembic if present — wildcard matches nothing gracefully
COPY alembic.in[i] ./
COPY alembi[c]/ ./alembic/

# Copy standalone frontend (no npm ci needed — deps are bundled)
COPY --from=frontend-build /app/frontend/.next/standalone/ ./frontend/
COPY --from=frontend-build /app/frontend/.next/static/ ./frontend/.next/static/
COPY --from=frontend-build /app/frontend/publi[c]/ ./frontend/public/

# Copy startup script
COPY start.sh ./
RUN chmod +x start.sh

EXPOSE 8000 3000

CMD ["./start.sh"]

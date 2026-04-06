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

# Install Node.js for Next.js production server
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Copy everything needed for pip install (README.md optional via wildcard)
COPY pyproject.toml README* ./
COPY src/ ./src/
RUN pip install --no-cache-dir .

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

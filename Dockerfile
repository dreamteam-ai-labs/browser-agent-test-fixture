# Multi-stage Dockerfile for browser-agent-test-fixture
# Stage 1: Build frontend
# Stage 2: Run backend + serve frontend

# --- Stage 1: Build Next.js frontend ---
FROM node:20-slim AS frontend-build

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci --production=false
COPY frontend/ ./
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

# Copy backend source + deps
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir .

# Validate all imports resolve — fail the build if deps are missing.
# This catches ghost dependencies and incomplete pyproject.toml before
# the container ever starts.
RUN python -c "from fixture.main import app; print('Import validation passed')"

# Copy alembic (if present)
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Copy built frontend
COPY --from=frontend-build /app/frontend/ ./frontend/
# Install production Node.js deps only
RUN cd frontend && npm ci --production

# Copy startup script
COPY start.sh ./
RUN chmod +x start.sh

EXPOSE 8000 3000

CMD ["./start.sh"]

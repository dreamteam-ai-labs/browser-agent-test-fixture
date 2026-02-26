# Stage 1: Build Next.js static export
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Python backend + static files
FROM python:3.11-slim
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY features.json ./

# Copy built frontend into the location main.py expects
COPY --from=frontend-build /app/frontend/out ./frontend/out

ENV PYTHONPATH=/app/src
EXPOSE 8000

CMD ["uvicorn", "fixture.main:app", "--host", "0.0.0.0", "--port", "8000"]

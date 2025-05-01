# syntax=docker/dockerfile:1
#################################
# 1. Build stage: install Python deps
#################################
FROM python:3.12.2-slim AS builder
WORKDIR /app

# Install build tools only for compiling any C extensions
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*  # combine & cleanup to reduce layer size :contentReference[oaicite:0]{index=0}

# Copy just requirements.txt to leverage build cache when deps don’t change
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt  # cached unless requirements.txt changes :contentReference[oaicite:1]{index=1}

# Copy application source
COPY backend/ .

#################################
# 2. Runtime stage: lean image
#################################
FROM python:3.12.2-slim AS runtime
WORKDIR /app

# Install only runtime OS deps (ffmpeg for audio processing)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl && \
    rm -rf /var/lib/apt/lists/*  # cleanup in same layer :contentReference[oaicite:2]{index=2}

# Create a non-root user for least-privilege execution
RUN groupadd --gid 10000 appgroup && \
    useradd --uid 10000 --gid appgroup --shell /usr/sbin/nologin \
      --create-home appuser  # use high UID/GID and nologin shell :contentReference[oaicite:3]{index=3}

# Copy installed Python packages & app code from builder
COPY --from=builder /usr/local/lib/python3.12 /usr/local/lib/python3.12  # site-packages :contentReference[oaicite:4]{index=4}
COPY --from=builder /app /app

USER appuser  # switch to non-root :contentReference[oaicite:5]{index=5}

EXPOSE 5000  # document service port :contentReference[oaicite:6]{index=6}

# Healthcheck for container orchestration readiness
HEALTHCHECK --interval=30s --timeout=3s \
  CMD curl -f http://localhost:5000/health || exit 1  # lets Docker know when the app is up :contentReference[oaicite:7]{index=7}

# Use array form to ensure signals are handled correctly
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]  # production-grade WSGI :contentReference[oaicite:8]{index=8}

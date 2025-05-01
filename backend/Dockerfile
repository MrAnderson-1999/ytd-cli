# syntax=docker/dockerfile:1
#################################
# 1. Build stage: install Python deps
#################################
FROM python:3.12.2-slim AS builder
WORKDIR /app

# Install build tools only for compiling any C extensions
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/* 

# Copy just requirements.txt to leverage build cache when deps don’t change
COPY ./requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt 

# Copy application source
COPY . .

#################################
# 2. Runtime stage: lean image
#################################
FROM python:3.12.2-slim AS runtime
WORKDIR /app

# Install only runtime OS deps (ffmpeg for audio processing)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl && \
    rm -rf /var/lib/apt/lists/* 

# Create a non-root user for least-privilege execution
RUN groupadd --gid 10000 appgroup && \
    useradd --uid 10000 --gid appgroup --shell /usr/sbin/nologin \
      --create-home appuser  

# Copy installed Python packages & app code from builder
COPY --from=builder /usr/local/lib/python3.12 /usr/local/lib/python3.12 
COPY --from=builder /app /app

# switch to non-root :contentReference[oaicite:5]{index=5}
USER appuser 

RUN pip install --no-cache-dir gunicorn

 # document service port :contentReference[oaicite:6]{index=6}
EXPOSE 5000

# Healthcheck for container orchestration readiness
# lets Docker know when the app is up :contentReference[oaicite:7]{index=7}
HEALTHCHECK --interval=30s --timeout=3s \
  CMD curl -f http://localhost:5000/health || exit 1  

# Use array form to ensure signals are handled correctly
  # production-grade WSGI :contentReference[oaicite:8]{index=8}
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]

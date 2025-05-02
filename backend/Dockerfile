FROM python:3.12-slim

# Install OS deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy and install Python deps (including gevent)
COPY backend/requirements.txt .
# Add gevent to requirements.txt or install it here:
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir gunicorn gevent

# Copy application
COPY backend/app.py .

EXPOSE 5000

# Now gevent is available
CMD ["gunicorn", "app:app",
     "--bind", "0.0.0.0:5000",
     "--worker-class", "gevent",
     "--timeout", "300"]

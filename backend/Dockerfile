FROM python:3.12-slim

# Install OS packages and clean up in one layer
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY ./requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir gunicorn

# Copy application code
COPY . .

# Expose the service port
EXPOSE 5000

# Use exec-array form to run Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]

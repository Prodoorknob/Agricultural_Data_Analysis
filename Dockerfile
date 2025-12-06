# USDA Agricultural Dashboard - Production Dockerfile
# Optimized for AWS App Runner deployment

# Use Python 3.11 slim image for smaller size
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install minimal system dependencies for Python packages
# build-essential: Required for compiling Python packages with C extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install Python dependencies
# --no-cache-dir: Don't cache pip packages (reduces image size)
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set environment variables for production
ENV PYTHONUNBUFFERED=1
ENV USE_S3=True

# Expose port 8080 (App Runner default)
EXPOSE 8080
ENV PORT=8080

# Health check (optional but recommended for App Runner)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080', timeout=5)"

# Run with gunicorn
# - app:server points to the server object in app.py
# - --bind 0.0.0.0:$PORT listens on all interfaces
# - --workers 2 uses 2 worker processes (tune based on container size)
# - --timeout 120 allows 2 minutes for slow requests (large data loads)
# - --access-logfile - logs requests to stdout
# - --error-logfile - logs errors to stdout
CMD gunicorn app:server \
    --bind 0.0.0.0:${PORT} \
    --workers 2 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -

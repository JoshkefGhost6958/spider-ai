# ==============================================================================
# Spider AI - Production Multi-Stage Container Image
# ==============================================================================
FROM python:3.12-slim-bookworm

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    DJANGO_SETTINGS_MODULE=config.settings

WORKDIR /app

# Install system utilities and Playwright dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ca-certificates \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    playwright install chromium

# Copy application source code
COPY . /app/

# Create runtime directories for media, staticfiles, and database storage
RUN mkdir -p /app/media/uploads /app/staticfiles /app/core/cache/screenshots

# Collect static assets
RUN python manage.py collectstatic --noinput || true

# Create a secure non-root user and grant permissions
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

# Expose HTTP port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Launch application via Gunicorn WSGI server
CMD ["sh", "-c", "python manage.py migrate --noinput && exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 3 --timeout 120 --access-logfile - --error-logfile -"]

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# Allowlist prevents local .env files, Git history and uploads entering the image.
COPY manage.py ./
COPY config/ ./config/
COPY apps/ ./apps/
COPY templates/ ./templates/
COPY static/ ./static/
# Build-only values are scoped to collectstatic and never used at runtime.
RUN DJANGO_SECRET_KEY=collectstatic-build-only \
    DATABASE_URL=postgresql://unused:unused@localhost/unused \
    python manage.py collectstatic --noinput \
    && chown -R app:app /app
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/health', timeout=6)"
CMD ["sh", "-c", "exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 120 --access-logfile - --error-logfile -"]

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# NEW: the dashboard is a folder plus two files
COPY app/ app/
COPY wsgi.py seed.py ./

# NEW: appuser also owns /app/instance (SQLite file when no DATABASE_URL is set)
RUN useradd --create-home appuser && mkdir -p /app/instance && chown appuser /app/instance
USER appuser

# NEW: port 5000
EXPOSE 5000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5000/health', timeout=2).status == 200 else 1)"

# NEW: wsgi:app, 2 worker processes
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "wsgi:app"]
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOST=0.0.0.0 \
    PORT=8080

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 appuser

# Explicit copies keep .env, Git history, and local files out of the image.
COPY --chown=appuser:appuser app ./app
COPY --chown=appuser:appuser frontend ./frontend

USER appuser
EXPOSE 8080
CMD ["python", "-m", "app.server"]

FROM python:3.12-slim

# Prevents Python from buffering stdout/stderr, so logs show up immediately
# with `docker logs`.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install dependencies first (separate layer so code changes don't bust the cache).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code.
COPY bot/ ./bot/
COPY tests/ ./tests/

# Directory where the SQLite database lives. Mount a volume here to persist
# data across container restarts/rebuilds:
#   docker run -v challenge_data:/app/data --env-file .env discord-challenge-bot
RUN mkdir -p /app/data
VOLUME ["/app/data"]

# Run as a non-root user for basic container hygiene.
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

CMD ["python", "-m", "bot.main"]

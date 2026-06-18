FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir requests beautifulsoup4

COPY scraper.py .

# Cache file lives in /cache so callers can mount a volume there
ENV CACHE_DIR=/cache
# Interval between runs in seconds (default: 30 min)
ENV INTERVAL=1800

CMD ["sh", "-c", "while true; do python scraper.py; sleep $INTERVAL; done"]

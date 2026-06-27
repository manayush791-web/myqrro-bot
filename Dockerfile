FROM python:3.12-slim

# System deps for Pillow + asyncpg
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc libpq-dev libffi-dev curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (layer-cached)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download fonts at build time (OFL-licensed, free for commercial use)
COPY scripts/download_fonts.sh scripts/download_fonts.sh
RUN chmod +x scripts/download_fonts.sh && bash scripts/download_fonts.sh

# Copy source
COPY . .

# Non-root user
RUN useradd -m -u 1000 bot && chown -R bot:bot /app
USER bot

EXPOSE ${PORT:-8000}

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -sf http://localhost:${PORT:-8000}/health || exit 1

CMD ["python", "main.py"]

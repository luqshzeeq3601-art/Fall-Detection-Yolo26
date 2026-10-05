# ElderCare Vision — Vision Ingestion & Inference Service
FROM python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install runtime dependencies for OpenCV and FFmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency configuration
COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -e ".[train]"

# Copy application source and configuration
COPY config/ ./config/
COPY models/ ./models/
COPY src/ ./src/

# Default entrypoint for vision stream processing
CMD ["python", "-m", "eldercare.live.manager"]

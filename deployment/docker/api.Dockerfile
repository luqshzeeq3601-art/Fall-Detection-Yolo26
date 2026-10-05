# ElderCare Vision — FastAPI Backend Service
FROM python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -e ".[train]"

# Copy source code and migrations
COPY alembic.ini .
COPY config/ ./config/
COPY models/ ./models/
COPY src/ ./src/

EXPOSE 8000

# Start FastAPI application via uvicorn
CMD ["uvicorn", "eldercare.api.app:app", "--host", "0.0.0.0", "--port", "8000"]

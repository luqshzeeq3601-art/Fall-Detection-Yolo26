# ElderCare Vision — Asynchronous VLM Agent Worker
FROM python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -e "."

# Copy application source
COPY config/ ./config/
COPY src/ ./src/

# Default entrypoint for asynchronous agent enrichment worker
CMD ["python", "-m", "eldercare.agents.service"]

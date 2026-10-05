# ElderCare Vision — All-in-One Streamlit Live Demo & Evaluation Dashboard
FROM python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true

# System libraries for OpenCV, video encoding and fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install project dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -e ".[train]"

# Copy application assets, models, and code
COPY config/ ./config/
COPY models/ ./models/
COPY src/ ./src/
COPY app/ ./app/
COPY apps/ ./apps/
COPY demo_data/ ./demo_data/
COPY streamlit_app.py .

EXPOSE 8501

# Run the unified Streamlit application
CMD ["streamlit", "run", "streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]

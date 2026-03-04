# Process BlueSky - Bluesky to X Cross-posting Service
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY main.sh ./
COPY run_tests.sh ./
COPY tests/ ./tests/

# Make scripts executable
RUN chmod +x main.sh run_tests.sh

# Environment variables
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# Labels
LABEL description="Process BlueSky - Bluesky to X Cross-posting Service" \
      version="1.0"

# Default command
CMD ["python3", "-m", "process_bluesky.main"]

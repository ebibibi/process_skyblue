#!/bin/bash
set -e

echo "🚀 Starting Process SkyBlue..."

# Pull latest repository state
echo "🔄 Pulling latest repository changes..."
git pull origin main

# Build Docker image
echo "🐳 Building Docker image..."
sudo docker build -t process-skyblue .

# Run the Docker container
echo "🎯 Running Process SkyBlue in Docker container..."
sudo docker run --rm \
    --env-file .env \
    -v "$(pwd)/data:/app/data" \
    process-skyblue

echo "🛑 Process SkyBlue stopped."

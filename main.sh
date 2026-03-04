#!/bin/bash
set -e

echo "🚀 Starting Process BlueSky..."

# Pull latest repository state
echo "🔄 Pulling latest repository changes..."
git pull origin main

# Build Docker image
echo "🐳 Building Docker image..."
sudo docker build -t process-bluesky .

# Run the Docker container
echo "🎯 Running Process BlueSky in Docker container..."
sudo docker run --rm \
    --env-file .env \
    -v "$(pwd)/data:/app/data" \
    process-bluesky

echo "🛑 Process BlueSky stopped."

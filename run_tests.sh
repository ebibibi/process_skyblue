#!/bin/bash

echo "🧪 Running Process BlueSky Tests..."

# Load environment variables
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Set PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"

# Run tests with coverage
echo "📊 Running unit tests with coverage..."
pytest tests/unit/ -v --cov=src/process_bluesky --cov-report=term-missing

echo "✅ All tests completed!"
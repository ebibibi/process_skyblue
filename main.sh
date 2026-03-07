#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "🚀 Starting Process BlueSky..."

# Pull latest repository state
echo "🔄 Pulling latest repository changes..."
git -C "$SCRIPT_DIR" pull origin main

# Run directly with scheduler venv (no Docker needed)
echo "🎯 Running Process BlueSky..."
set -a
source "$SCRIPT_DIR/.env"
set +a
PYTHONPATH="$SCRIPT_DIR/src" /home/ebi/scheduler/venv/bin/python3 -m process_bluesky.main

echo "🛑 Process BlueSky stopped."

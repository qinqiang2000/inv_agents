#!/bin/bash

# Invoice Field Recommender Agent - Startup Script

# Set working directory to agents folder (required for context access)
cd /Users/qinqiang02/colab/codespace/ai/invoice_engine_3rd/agents

# Activate virtual environment
if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
else
    echo "❌ Virtual environment not found at .venv/bin/activate"
    echo "Please create a virtual environment first:"
    echo "  python3 -m venv .venv"
    echo "  source .venv/bin/activate"
    echo "  pip install -r requirements.txt"
    exit 1
fi

# Load environment variables from .env.prod file
if [ -f .env.prod ]; then
    source .env.prod
    echo "✅ Loaded environment variables from .env.prod"
else
    echo "⚠️  .env.prod file not found (optional)"
fi

# Check if dependencies are installed
if ! python -c "import fastapi" 2>/dev/null; then
    echo "⚠️  Dependencies not installed. Installing now..."
    pip install -r requirements.txt
fi

# Print startup info
echo "=========================================="
echo "Invoice Field Recommender Agent"
echo "=========================================="
echo "Working directory: $(pwd)"
echo "API will be available at: http://localhost:8000"
echo "Chat UI: http://localhost:8000"
echo "API Docs: http://localhost:8000/docs"
echo "=========================================="
echo ""

# Start the FastAPI server
uvicorn app:app --host 0.0.0.0 --port 8000 --reload

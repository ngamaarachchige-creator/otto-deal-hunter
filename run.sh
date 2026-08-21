#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

VENV_PATH="$DIR/.venv"
SCRATCH_ENV="/Users/nethukagamaarachcige/.gemini/antigravity-ide/scratch/test_env"

if [ -d "$SCRATCH_ENV" ]; then
    PYTHON_EXEC="$SCRATCH_ENV/bin/python3"
elif [ -d "$VENV_PATH" ]; then
    PYTHON_EXEC="$VENV_PATH/bin/python3"
else
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_PATH"
    "$VENV_PATH/bin/pip" install -r requirements.txt
    PYTHON_EXEC="$VENV_PATH/bin/python3"
fi

echo "=========================================================="
echo "🚗 Starting Lanka Car Hunter (Auto Flip & Scraping Hub)..."
echo "🌐 Local Dashboard: http://localhost:8000"
echo "=========================================================="

"$PYTHON_EXEC" -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

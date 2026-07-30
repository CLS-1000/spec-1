#!/usr/bin/env bash
# Development environment setup for SPEC-1.
# Run from any directory — paths are resolved relative to the script's repo root.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"

echo "==> Setting up SPEC-1 development environment"
echo "    Repo: $REPO_ROOT"

# 1. Check Python version (≥3.9)
python3 -c "
import sys
major, minor = sys.version_info[:2]
if (major, minor) < (3, 9):
    print(f'ERROR: Python 3.9+ required (found {major}.{minor})')
    sys.exit(1)
print(f'    Python {major}.{minor} — OK')
"

# 2. Create .env if it doesn't exist
if [ ! -f .env ]; then
    cp .env.example .env
    echo "    Created .env from .env.example"
    echo "    ACTION REQUIRED: set ANTHROPIC_API_KEY in .env"
else
    echo "    .env already exists — skipping"
fi

# 3. Install package + dev deps
echo "==> Installing dependencies"
if [ "${1:-}" = "--quant" ]; then
    python3 -m pip install -e ".[dev,quant]"
else
    python3 -m pip install -e ".[dev]"
fi

# 4. Create generated/ directory
mkdir -p generated/briefs generated/reports generated/exports
echo "    Created generated/ directories"

# 5. Smoke test
echo "==> Running smoke test"
PYTHONPATH="$REPO_ROOT/src" python3 -c "
from spec1_engine.core.engine import Engine
print('    Engine import — OK')
"
PYTHONPATH="$REPO_ROOT/src" python3 -c "
from spec1_api.main import app
print('    API import — OK')
"
PYTHONPATH="$REPO_ROOT/src" python3 -c "
import mcp_server
print('    MCP server import — OK')
"

echo ""
echo "Setup complete. Next steps:"
echo "  1. Edit .env and set ANTHROPIC_API_KEY"
echo "  2. make test          # verify full test suite"
echo "  3. make cycle         # run one-shot intelligence cycle"
echo "  4. make run           # start API server at http://localhost:8000"

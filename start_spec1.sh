
#!/usr/bin/env bash
# ============================================================
# SPEC-1 — Environment Setup Script
# Run: bash start_spec1.sh
# ============================================================

set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

echo "============================================================"
echo "  SPEC-1 — Loading Environment"
echo "  $(date)"
echo "============================================================"

# 1 — Set PYTHONPATH
export PYTHONPATH="$REPO_DIR/src"
echo "[ok] PYTHONPATH=$PYTHONPATH"

# 2 — Load .env without BOM
ENV_FILE="$REPO_DIR/.env"
if [ -f "$ENV_FILE" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
        # Strip BOM and leading/trailing whitespace
        line=$(echo "$line" | sed 's/^\xef\xbb\xbf//' | tr -d '\r' | xargs)
        # Skip comments and empty lines
        [[ "$line" =~ ^#.*$ ]] && continue
        [[ -z "$line" ]] && continue
        export "$line"
        key=$(echo "$line" | cut -d= -f1)
        echo "[ok] Loaded: $key"
    done < "$ENV_FILE"
else
    echo "[warn] No .env file found at $ENV_FILE"
fi

# 3 — Verify API key
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "[error] ANTHROPIC_API_KEY not set — brief generation will fail"
else
    echo "[ok] ANTHROPIC_API_KEY loaded: ${ANTHROPIC_API_KEY:0:20}..."
fi

# 4 — Activate venv if present
if [ -f "$REPO_DIR/.venv/bin/activate" ]; then
    source "$REPO_DIR/.venv/bin/activate"
    echo "[ok] venv activated"
elif [ -f "$REPO_DIR/.venv/Scripts/activate" ]; then
    source "$REPO_DIR/.venv/Scripts/activate"
    echo "[ok] venv activated (Windows)"
fi

echo "============================================================"
echo "  Commands:"
echo "  python -m spec1_core.app.cycle            # OSINT cycle (local model)"
echo "  python -m spec1_core.app.cycle --triage-only  # No model: harvest + gates + rules"
echo "  python -m spec1_core.congressional.cycle  # Congressional"
echo "  python -m spec1_api.main                  # FastAPI service"
echo "  python -m spec1_core.workspace list       # Open cases"
echo "  pytest tests/ -q                          # Run all tests"
echo "============================================================"

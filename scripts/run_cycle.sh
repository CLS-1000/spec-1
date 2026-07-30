#!/usr/bin/env bash
# Run a SPEC-1 intelligence cycle with optional flags.
# Run from any directory — paths are resolved relative to the script's repo root.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
export PYTHONPATH="$REPO_ROOT/src"

usage() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  --quant       Run the quantitative market signal pipeline"
    echo "  --dry-run     Harvest and score signals; skip investigation and briefing"
    echo "  --brief-only  Backfill briefs for existing records (no new cycle)"
    echo "  --help        Show this message"
    echo ""
    echo "Examples:"
    echo "  $0                    # Standard cycle"
    echo "  $0 --quant            # Market signal pipeline"
    echo "  $0 --brief-only       # Regenerate briefs from last cycle's records"
}

QUANT=false
DRY_RUN=false
BRIEF_ONLY=false

for arg in "$@"; do
    case $arg in
        --quant)      QUANT=true ;;
        --dry-run)    DRY_RUN=true ;;
        --brief-only) BRIEF_ONLY=true ;;
        --help)       usage; exit 0 ;;
        *)            echo "Unknown option: $arg"; usage; exit 1 ;;
    esac
done

cd "$REPO_ROOT"

if [ "$BRIEF_ONLY" = true ]; then
    echo "==> Generating briefs from existing records"
    python3 -m spec1_engine.tools.historical_briefs
    exit 0
fi

if [ "$QUANT" = true ]; then
    echo "==> Running quantitative market signal pipeline"
    python3 -m spec1_engine.quant.cycle
    exit 0
fi

echo "==> Starting SPEC-1 cycle ($(date -u '+%Y-%m-%dT%H:%M:%SZ'))"

if [ "$DRY_RUN" = true ]; then
    echo "    Mode: dry-run (harvest + score only)"
    python3 - <<'PYEOF'
from spec1_engine.signal.harvester import harvest_all
from spec1_engine.signal.parser import parse_signal
from spec1_engine.signal.scorer import score_signal

signals = list(harvest_all())
print(f"    Harvested: {len(signals)} signals")

opportunities = []
for sig in signals:
    parsed = parse_signal(sig)
    opp = score_signal(sig, parsed)
    if opp is not None:
        opportunities.append(opp)

print(f"    Opportunities: {len(opportunities)} passed all 4 gates")
PYEOF
else
    python3 -m spec1_engine.app.cycle
fi

echo "==> Cycle complete ($(date -u '+%Y-%m-%dT%H:%M:%SZ'))"

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
    echo "  --triage      Harvest + 4 gates + deterministic rules, stored as rule_based (no model, no brief)"
    echo "  --dry-run     Harvest and score signals; store nothing"
    echo "  --brief-only  Backfill briefs for existing records (no new cycle)"
    echo "  --help        Show this message"
    echo ""
    echo "Examples:"
    echo "  $0                    # Standard cycle"
    echo "  $0 --triage           # What the GitHub Actions cycle runs"
    echo "  $0 --brief-only       # Regenerate briefs from last cycle's records"
}

TRIAGE=false
DRY_RUN=false
BRIEF_ONLY=false

for arg in "$@"; do
    case $arg in
        --triage)     TRIAGE=true ;;
        --quant)      echo "--quant: there is no quant pipeline in spec1_core (it lived only in the archived spec1_engine)."; exit 1 ;;
        --dry-run)    DRY_RUN=true ;;
        --brief-only) BRIEF_ONLY=true ;;
        --help)       usage; exit 0 ;;
        *)            echo "Unknown option: $arg"; usage; exit 1 ;;
    esac
done

cd "$REPO_ROOT"

if [ "$BRIEF_ONLY" = true ]; then
    echo "==> Generating briefs from existing records"
    python3 -m spec1_core.tools.historical_briefs
    exit 0
fi

if [ "$TRIAGE" = true ]; then
    echo "==> Running triage-only cycle (no model)"
    python3 -m spec1_core.app.cycle --triage-only
    exit 0
fi

echo "==> Starting SPEC-1 cycle ($(date -u '+%Y-%m-%dT%H:%M:%SZ'))"

if [ "$DRY_RUN" = true ]; then
    echo "    Mode: dry-run (harvest + score only)"
    python3 - <<'PYEOF'
from spec1_core.signal.harvester import harvest_all
from spec1_core.signal.parser import parse_signal
from spec1_core.signal.scorer import score_signal

signals = harvest_all()["signals"]
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
    python3 -m spec1_core.app.cycle
fi

echo "==> Cycle complete ($(date -u '+%Y-%m-%dT%H:%M:%SZ'))"

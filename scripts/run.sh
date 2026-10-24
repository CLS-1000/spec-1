#!/bin/bash
# SPEC-1 // ONE WORLD CITIZEN — daily intelligence run
set -e

cd ~/spec-1
source venv/bin/activate
export ANTHROPIC_API_KEY=$(grep ANTHROPIC_API_KEY .env | cut -d= -f2 | tr -d '\r\n')

TODAY=$(date +%Y-%m-%d)

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  SPEC-1 // ONE WORLD CITIZEN"
echo "  $TODAY $(date -u '+%H:%M UTC')"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Run cycle
python -m spec1_core.app.cycle

# Render PDF if brief exists
BRIEF="briefs/spec1_brief_${TODAY}.md"
if [ -f "$BRIEF" ]; then
    OUT="/mnt/c/Users/mjlak/Desktop/owc_${TODAY}.pdf"
    PYTHONPATH=src python -m spec1_core.tools.pdf_render \
        --brief-md "$BRIEF" \
        --out "$OUT"
    echo ""
    echo "  Brief: $OUT"
    echo "  Open it."
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

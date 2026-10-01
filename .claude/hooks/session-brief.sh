#!/usr/bin/env bash
# SessionStart hook: injects the repo's open loops + git state into every
# Claude Code session before the first prompt.
#
# Fails open. If anything here errors, the session still starts.

set -uo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "$PWD")"
LEDGER="$REPO_ROOT/.claude/OPEN_LOOPS.md"

BRIEF=""

BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
if [ -n "$BRANCH" ]; then
    BRIEF+="## Repo state"$'\n'
    BRIEF+="branch: ${BRANCH}"$'\n'
    DIRTY="$(git status --short 2>/dev/null | head -12)"
    if [ -n "$DIRTY" ]; then
        BRIEF+="uncommitted:"$'\n'"${DIRTY}"$'\n'
    else
        BRIEF+="working tree clean"$'\n'
    fi
    BRIEF+=$'\n'
fi

if [ -f "$LEDGER" ]; then
    LOOPS="$(awk '/^## Open/{f=1;next} /^## /{f=0} f' "$LEDGER" | grep -v '^\s*$' || true)"
    COUNT="$(printf '%s' "$LOOPS" | grep -c '^-' || true)"
    if [ -n "$LOOPS" ]; then
        BRIEF+="## Open loops (${COUNT}) — from .claude/OPEN_LOOPS.md"$'\n'
        BRIEF+="${LOOPS}"$'\n\n'
        BRIEF+="Do not act on these unless asked. Raise one only if the current task touches it."$'\n'
    fi
fi

[ -z "$BRIEF" ] && exit 0

if command -v jq >/dev/null 2>&1; then
    printf '%s' "$BRIEF" | jq -Rs \
      '{hookSpecificOutput:{hookEventName:"SessionStart",additionalContext:.}}'
else
    ESCAPED=$(printf '%s' "$BRIEF" \
        | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' -e ':a' -e 'N' -e '$!ba' -e 's/\n/\\n/g')
    printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}\n' "$ESCAPED"
fi

exit 0

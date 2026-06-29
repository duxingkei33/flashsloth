#!/bin/bash
# Auto git commit + push for flashsloth
# Runs as no_agent script, stdout = delivered verbatim when non-empty

REPO="/opt/data/flashsloth"
cd "$REPO" || exit 1

# Check for changes
if ! git diff --quiet HEAD 2>/dev/null; then
    # Count changed files
    CHANGED=$(git diff --name-only HEAD | wc -l)
    
    # Generate version tag
    TODAY=$(date +%Y%m%d)
    LATEST_TAG=$(git tag -l "${TODAY}V*" 2>/dev/null | sort -V | tail -1)
    
    if [ -z "$LATEST_TAG" ]; then
        NEW_TAG="${TODAY}V1"
    else
        LAST_NUM=$(echo "$LATEST_TAG" | sed "s/${TODAY}V//")
        NEW_TAG="${TODAY}V$((LAST_NUM + 1))"
    fi
    
    # Auto-commit message based on changes
    SUMMARY=$(git diff --name-only HEAD | head -5 | tr '\n' ' ')
    
    git add -A
    git commit -m "auto: ${CHANGED} files changed [${SUMMARY:0:80}]"
    git tag -a "$NEW_TAG" -m "auto: ${CHANGED} files changed"
    git push origin main --tags 2>&1
    
    echo "📦 Auto-pushed ${CHANGED} file(s) → tag ${NEW_TAG}"
fi

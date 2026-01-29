#!/bin/bash
# Claude Container Entrypoint (Client)
#
# Tool symlinks are pre-generated on the host by install.sh.
# The tools/ directory (containing bin/ and tools.d/) is mounted read-only.
#
# Runs project-specific client setup if configured in /workspace/.claude-container/config.json

set -e

PROJECT_CONFIG="/workspace/.claude-container/config.json"

# Run client setup if configured
if [ -f "$PROJECT_CONFIG" ]; then
    # Extract client setup script path from JSON config
    SETUP_SCRIPT=$(python3 -c "
import json
import sys
try:
    with open('$PROJECT_CONFIG') as f:
        config = json.load(f)
    setup = config.get('setup', '')
    # New format: setup is a dict with 'client' key
    if isinstance(setup, dict):
        print(setup.get('client', ''))
    else:
        print('')
except Exception as e:
    print('', file=sys.stderr)
" 2>/dev/null)

    if [ -n "$SETUP_SCRIPT" ]; then
        FULL_SETUP_PATH="/workspace/$SETUP_SCRIPT"
        if [ -f "$FULL_SETUP_PATH" ]; then
            echo "Running client setup: $SETUP_SCRIPT"
            cd /workspace
            bash "$FULL_SETUP_PATH" || echo "WARNING: Client setup failed"
        fi
    fi
fi

# Execute the main command
exec "$@"

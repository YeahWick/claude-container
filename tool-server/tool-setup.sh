#!/bin/bash
# Tool Server Entrypoint
#
# Runs per-tool setup scripts from tools.d/ directories, then executes the main command.
# Each tool can have its own setup script: /app/tools.d/{tool}/setup.sh
#
# Also runs project-specific setup if configured in /workspace/.claude-container/config.json
# The config file specifies the setup script path relative to the project root.

set -e

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') SETUP $1"
}

# Create necessary directories
mkdir -p /run/sockets 2>/dev/null || true

TOOLS_DIR="${TOOLS_DIR:-/app/tools.d}"
PROJECT_CONFIG="/workspace/.claude-container/config.json"

# Run tool-specific setup scripts from tools.d/
if [ -d "$TOOLS_DIR" ]; then
    tool_count=0
    for tool_dir in "$TOOLS_DIR"/*/; do
        [ -d "$tool_dir" ] || continue
        tool_name="$(basename "$tool_dir")"
        setup_script="$tool_dir/setup.sh"

        if [ -f "$setup_script" ]; then
            log "Running setup for: $tool_name"
            if bash "$setup_script"; then
                log "Setup complete: $tool_name"
            else
                log "WARNING: Setup failed for $tool_name (exit $?)"
            fi
        fi
        tool_count=$((tool_count + 1))
    done
    log "Found $tool_count tool(s) in $TOOLS_DIR"
fi

# Run project-specific server setup if configured
# Config formats:
#   New: {"setup": {"server": "path/to/setup.sh", "client": "path/to/client.sh"}}
#   Legacy: {"setup": "path/to/setup.sh"}
if [ -f "$PROJECT_CONFIG" ]; then
    log "Found project config at $PROJECT_CONFIG"

    # Extract server setup script path from JSON config
    SETUP_SCRIPT=$(python3 -c "
import json
import sys
try:
    with open('$PROJECT_CONFIG') as f:
        config = json.load(f)
    setup = config.get('setup', '')
    # New format: setup is a dict with 'server' key
    if isinstance(setup, dict):
        print(setup.get('server', ''))
    # Legacy format: setup is a string path
    elif isinstance(setup, str):
        print(setup)
    else:
        print('')
except Exception as e:
    print('', file=sys.stderr)
" 2>/dev/null)

    if [ -n "$SETUP_SCRIPT" ]; then
        # Resolve path relative to workspace
        FULL_SETUP_PATH="/workspace/$SETUP_SCRIPT"

        if [ -f "$FULL_SETUP_PATH" ]; then
            log "Running server setup: $SETUP_SCRIPT"
            cd /workspace
            if bash "$FULL_SETUP_PATH"; then
                log "Server setup complete"
            else
                log "WARNING: Server setup failed (exit $?)"
            fi
        else
            log "WARNING: Server setup script not found: $FULL_SETUP_PATH"
        fi
    else
        log "No server setup script configured in $PROJECT_CONFIG"
    fi
else
    log "No project config found at $PROJECT_CONFIG (optional)"
fi

log "Setup finished, starting server"

# Execute the main command
exec "$@"

#!/bin/bash
# Tool Server Entrypoint
#
# Runs per-tool setup scripts from tools.d/ directories, then executes the main command.
# Each tool can have its own setup script: /app/tools.d/{tool}/setup.sh

set -e

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') SETUP $1"
}

# Create necessary directories
mkdir -p /run/sockets 2>/dev/null || true

TOOLS_DIR="${TOOLS_DIR:-/app/tools.d}"

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

log "Setup finished, starting server"

# Execute the main command
exec "$@"

#!/bin/bash
# Tool Container Entrypoint
#
# Runs per-tool setup scripts from tools.d/ directories, then executes the main command.
# Each tool can have its own setup script: /app/tools.d/{tool}/setup.sh
# Also supports legacy setup scripts in /app/setup.d/{tool}.sh

set -e

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') SETUP $1"
}

# Create necessary directories
mkdir -p /run/plugins 2>/dev/null || true

TOOLS_DIR="${TOOLS_DIR:-/app/tools.d}"
SETUP_DIR="${SETUP_DIR:-/app/setup.d}"

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

# Run legacy setup scripts from setup.d/ (backwards compatibility)
if [ -d "$SETUP_DIR" ]; then
    for script in "$SETUP_DIR"/*.sh; do
        [ -f "$script" ] || continue
        name="$(basename "$script" .sh)"
        log "Running legacy setup: $name"
        if bash "$script"; then
            log "Legacy setup complete: $name"
        else
            log "WARNING: Legacy setup failed for $name (exit $?)"
        fi
    done
fi

log "Setup finished, starting server"

# Execute the main command
exec "$@"

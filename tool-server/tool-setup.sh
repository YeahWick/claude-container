#!/bin/bash
# Tool Server Entrypoint
#
# Runs per-tool setup scripts from tools.d/ directories, then executes the main command.
# Each tool can have its own setup script: /app/tools.d/{tool}/setup.sh
#
# Also runs project-specific setup if /workspace/.claude-container/setup.sh exists.
# This allows projects to install dependencies (npm install, pip install, etc.)

set -e

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') SETUP $1"
}

# Create necessary directories
mkdir -p /run/sockets 2>/dev/null || true

TOOLS_DIR="${TOOLS_DIR:-/app/tools.d}"
PROJECT_SETUP="/workspace/.claude-container/setup.sh"

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

# Run project-specific setup if it exists
# This allows projects to define their own dependency installation
if [ -f "$PROJECT_SETUP" ]; then
    log "Running project setup from $PROJECT_SETUP"
    if bash "$PROJECT_SETUP"; then
        log "Project setup complete"
    else
        log "WARNING: Project setup failed (exit $?)"
    fi
else
    log "No project setup found at $PROJECT_SETUP (optional)"
fi

log "Setup finished, starting server"

# Execute the main command
exec "$@"

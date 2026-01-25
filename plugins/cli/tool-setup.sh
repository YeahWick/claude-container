#!/bin/bash
# Tool Container Entrypoint
#
# Runs per-tool setup scripts from /app/setup.d/ then executes the main command.
# Each tool can have its own setup script: /app/setup.d/{tool}.sh

set -e

# Create necessary directories
mkdir -p /run/plugins 2>/dev/null || true

# Run per-tool setup scripts
SETUP_DIR="${SETUP_DIR:-/app/setup.d}"
if [ -d "$SETUP_DIR" ]; then
    for script in "$SETUP_DIR"/*.sh; do
        [ -f "$script" ] || continue
        echo "Setup: $(basename "$script" .sh)"
        bash "$script" || echo "  Warning: setup failed"
    done
fi

# Execute the main command
exec "$@"

#!/bin/bash
# Claude Container Entrypoint
#
# Auto-generates CLI wrapper symlinks from tools.d/ directory.
# Each tool subdirectory in tools.d/ gets a symlink created in
# /home/claude/bin/ pointing to the cli-wrapper script.
#
# This eliminates the need to manually create symlinks when adding tools.

set -e

BIN_DIR="/home/claude/bin"
TOOLS_DIR="${TOOLS_DIR:-/app/tools.d}"
CLI_WRAPPER="$BIN_DIR/cli-wrapper"

# Auto-generate symlinks from tools.d/
if [ -d "$TOOLS_DIR" ] && [ -f "$CLI_WRAPPER" ]; then
    for tool_dir in "$TOOLS_DIR"/*/; do
        [ -d "$tool_dir" ] || continue
        tool_name="$(basename "$tool_dir")"
        symlink="$BIN_DIR/$tool_name"

        # Skip if tool name is cli-wrapper itself
        [ "$tool_name" = "cli-wrapper" ] && continue

        # Create symlink if it doesn't already exist (or is stale)
        if [ ! -e "$symlink" ] || [ -L "$symlink" ]; then
            ln -sf cli-wrapper "$symlink"
        fi
    done
fi

# Execute the main command
exec "$@"

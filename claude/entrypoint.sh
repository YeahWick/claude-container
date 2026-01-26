#!/bin/bash
# Claude Container Entrypoint
#
# Auto-generates CLI wrapper symlinks from tools.d/ directory, then starts
# a lightweight background poller that watches for new tools added at runtime.
#
# Initial scan: creates symlinks for all tools found in tools.d/
# Background poller: checks every few seconds for new tool directories
#   and creates missing symlinks on the fly (hot-loading).

set -e

BIN_DIR="/home/claude/bin"
TOOLS_DIR="${TOOLS_DIR:-/app/tools.d}"
CLI_WRAPPER="$BIN_DIR/cli-wrapper"
POLL_INTERVAL="${TOOL_POLL_INTERVAL:-5}"

# Generate symlinks for all tools currently in tools.d/
sync_symlinks() {
    [ -d "$TOOLS_DIR" ] && [ -f "$CLI_WRAPPER" ] || return 0

    for tool_dir in "$TOOLS_DIR"/*/; do
        [ -d "$tool_dir" ] || continue
        tool_name="$(basename "$tool_dir")"
        symlink="$BIN_DIR/$tool_name"

        # Skip cli-wrapper itself
        [ "$tool_name" = "cli-wrapper" ] && continue

        # Create symlink if missing or already a symlink (update)
        if [ ! -e "$symlink" ] || [ -L "$symlink" ]; then
            ln -sf cli-wrapper "$symlink"
        fi
    done
}

# Background poller — watches for new tool directories and creates symlinks
poll_for_new_tools() {
    while true; do
        sleep "$POLL_INTERVAL"
        sync_symlinks 2>/dev/null || true
    done
}

# Initial sync
sync_symlinks

# Start background poller (only if tools.d exists and is a directory)
if [ -d "$TOOLS_DIR" ] && [ -f "$CLI_WRAPPER" ]; then
    poll_for_new_tools &
fi

# Execute the main command
exec "$@"

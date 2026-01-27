#!/bin/bash
# Install script for Claude Container
#
# Sets up host directories, copies tool definitions, and generates client wrappers.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude-container}"

echo "Claude Container - Installation"
echo "================================"
echo ""
echo "Installing to: $CLAUDE_HOME"
echo ""

# Create host directories
echo "Creating directories..."
mkdir -p "$CLAUDE_HOME"/{client,sockets,config,tools.d}

# Set permissions
# UID 1000 = container user (tool server writes to sockets)
echo "Setting permissions..."
chmod 755 "$CLAUDE_HOME"/client
chmod 770 "$CLAUDE_HOME"/sockets
chmod 755 "$CLAUDE_HOME"/config
chmod 755 "$CLAUDE_HOME"/tools.d

# Copy tool-client script
echo "Installing tool client..."
cp "$REPO_DIR"/client/tool-client "$CLAUDE_HOME"/client/
chmod +x "$CLAUDE_HOME"/client/tool-client

# Copy built-in tool definitions
echo "Installing tool definitions..."
if [ -d "$REPO_DIR/tools.d" ]; then
    for tool_dir in "$REPO_DIR"/tools.d/*/; do
        [ -d "$tool_dir" ] || continue
        tool_name="$(basename "$tool_dir")"
        dest="$CLAUDE_HOME/tools.d/$tool_name"

        # Copy tool definition (don't overwrite user customizations)
        if [ ! -d "$dest" ]; then
            cp -r "$tool_dir" "$dest"
            echo "  Added tool: $tool_name"
        else
            # Update tool.json but preserve user's restricted/setup scripts
            if [ -f "$tool_dir/tool.json" ]; then
                cp "$tool_dir/tool.json" "$dest/tool.json"
            fi
            echo "  Updated tool: $tool_name"
        fi
    done
fi

# Auto-generate client symlinks from tools.d
echo "Generating client symlinks..."
for tool_dir in "$CLAUDE_HOME"/tools.d/*/; do
    [ -d "$tool_dir" ] || continue
    tool_name="$(basename "$tool_dir")"
    symlink="$CLAUDE_HOME/client/$tool_name"

    # Skip if tool name is tool-client
    [ "$tool_name" = "tool-client" ] && continue

    # Create or update symlink
    ln -sf tool-client "$symlink"
    echo "  $tool_name -> tool-client"
done

# Copy default configs
echo "Installing default configurations..."
cp "$REPO_DIR"/config/* "$CLAUDE_HOME"/config/ 2>/dev/null || true

echo ""
echo "Installation complete!"
echo ""
echo "Directory structure:"
echo "  $CLAUDE_HOME/"
echo "  ├── client/        # Tool client + auto-generated symlinks"
echo "  ├── sockets/       # Tool server Unix sockets (one per instance)"
echo "  ├── config/        # Configuration files"
echo "  └── tools.d/       # Tool definitions (auto-discovered)"
echo ""

# Show discovered tools
echo "Registered tools:"
for tool_dir in "$CLAUDE_HOME"/tools.d/*/; do
    [ -d "$tool_dir" ] || continue
    tool_name="$(basename "$tool_dir")"
    has_manifest="no"
    has_setup="no"
    has_restricted="no"
    [ -f "$tool_dir/tool.json" ] && has_manifest="yes"
    [ -f "$tool_dir/setup.sh" ] && has_setup="yes"
    [ -f "$tool_dir/restricted.sh" ] || [ -f "$tool_dir/restricted.py" ] && has_restricted="yes"
    echo "  $tool_name (manifest=$has_manifest, setup=$has_setup, restricted=$has_restricted)"
done
echo ""

echo "Next steps:"
echo "  1. Set your API key:     export ANTHROPIC_API_KEY=your_key"
echo "  2. Build containers:     docker compose build"
echo "  3. Start Claude:         ./scripts/run.sh"
echo ""
echo "To add a new tool:"
echo "  1. Create: $CLAUDE_HOME/tools.d/mytool/tool.json"
echo '     Content: {"binary": "/usr/bin/mytool", "timeout": 300}'
echo "  2. (Optional) Add: setup.sh, restricted.sh, restricted.py"
echo "  3. Re-run: ./scripts/install.sh  (generates symlinks)"
echo "  4. Rebuild: docker compose build  (if binary needs installing)"
echo ""
echo "Or from a tool repo:"
echo "  cp -r /path/to/my-tool-repo $CLAUDE_HOME/tools.d/mytool"
echo "  ./scripts/install.sh"
echo ""

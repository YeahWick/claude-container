#!/bin/bash
# Install script for Claude Container
#
# Sets up host directories, copies tool definitions, and generates client wrappers.
# The tools/ directory contains both bin/ (client + symlinks) and tools.d/ (definitions)
# so that bin symlinks use simple relative paths to tool-client.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.config/claude-container}"

echo "Claude Container - Installation"
echo "================================"
echo ""
echo "Installing to: $CLAUDE_HOME"
echo ""

# Create host directories
# tools/ is a single mount containing both bin/ and tools.d/
echo "Creating directories..."
mkdir -p "$CLAUDE_HOME"/{tools/bin,tools/tools.d,sockets,config,repo}

# Set permissions
# UID 1000 = container user (tool server writes to sockets)
echo "Setting permissions..."
chmod 755 "$CLAUDE_HOME"/tools
chmod 755 "$CLAUDE_HOME"/tools/bin
chmod 755 "$CLAUDE_HOME"/tools/tools.d
chmod 770 "$CLAUDE_HOME"/sockets
chmod 755 "$CLAUDE_HOME"/config

# Copy tool-client script
echo "Installing tool client..."
cp "$REPO_DIR"/client/tool-client "$CLAUDE_HOME"/tools/bin/
chmod +x "$CLAUDE_HOME"/tools/bin/tool-client

# Copy built-in tool definitions
echo "Installing tool definitions..."
if [ -d "$REPO_DIR/tools.d" ]; then
    for tool_dir in "$REPO_DIR"/tools.d/*/; do
        [ -d "$tool_dir" ] || continue
        tool_name="$(basename "$tool_dir")"
        dest="$CLAUDE_HOME/tools/tools.d/$tool_name"

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
# Symlinks are relative: git -> tool-client (both in bin/)
echo "Generating client symlinks..."
for tool_dir in "$CLAUDE_HOME"/tools/tools.d/*/; do
    [ -d "$tool_dir" ] || continue
    tool_name="$(basename "$tool_dir")"
    symlink="$CLAUDE_HOME/tools/bin/$tool_name"

    # Skip if tool name is tool-client
    [ "$tool_name" = "tool-client" ] && continue

    # Create or update symlink (relative within bin/)
    ln -sf tool-client "$symlink"
    echo "  $tool_name -> tool-client"
done

# Copy default configs
echo "Installing default configurations..."
cp "$REPO_DIR"/config/* "$CLAUDE_HOME"/config/ 2>/dev/null || true

# Create .env template if it doesn't exist
if [ ! -f "$CLAUDE_HOME/.env" ]; then
    cat > "$CLAUDE_HOME/.env" << 'EOF'
# Claude Container environment configuration
# Uncomment and set your API keys:

# ANTHROPIC_API_KEY=your_key_here
# GITHUB_TOKEN=your_token_here
EOF
    echo "Created .env template at $CLAUDE_HOME/.env"
fi

# Copy repo files for CLI access
echo "Installing repo files..."
cp "$REPO_DIR"/podman-compose.yaml "$CLAUDE_HOME"/repo/
cp -r "$REPO_DIR"/claude "$CLAUDE_HOME"/repo/
cp -r "$REPO_DIR"/tool-server "$CLAUDE_HOME"/repo/
cp -r "$REPO_DIR"/tools.d "$CLAUDE_HOME"/repo/
cp -r "$REPO_DIR"/scripts "$CLAUDE_HOME"/repo/
cp -r "$REPO_DIR"/catalog "$CLAUDE_HOME"/repo/

echo ""
echo "Installation complete!"
echo ""
echo "Directory structure:"
echo "  $CLAUDE_HOME/"
echo "  ├── tools/           # Single mount for client + tool definitions"
echo "  │   ├── bin/         # tool-client + auto-generated symlinks"
echo "  │   └── tools.d/     # Tool definitions (auto-discovered)"
echo "  ├── sockets/         # Tool server Unix sockets (one per instance)"
echo "  ├── config/          # Configuration files"
echo "  └── .env             # API keys (ANTHROPIC_API_KEY, GITHUB_TOKEN)"
echo ""

# Show discovered tools
echo "Registered tools:"
for tool_dir in "$CLAUDE_HOME"/tools/tools.d/*/; do
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
echo "  1. Set your API key:     echo 'ANTHROPIC_API_KEY=your_key' >> $CLAUDE_HOME/.env"
echo "  2. Build containers:     claude-container build"
echo "  3. Start Claude:         claude-container"
echo ""
echo "Or run everything at once:"
echo "  claude-container setup"
echo ""
echo "To add tools:"
echo "  claude-container tools list              # See available tools"
echo "  claude-container tools add npm           # Add from catalog"
echo "  claude-container tools add mytool --url https://github.com/user/tool"
echo ""
echo "After adding tools, rebuild containers:"
echo "  claude-container build"
echo ""

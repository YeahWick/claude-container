#!/bin/bash
# Install script for Claude Container v2
#
# Sets up host directories and copies default configuration files.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude-container}"

echo "Claude Container v2 - Installation"
echo "==================================="
echo ""
echo "Installing to: $CLAUDE_HOME"
echo ""

# Create host directories
echo "Creating directories..."
mkdir -p "$CLAUDE_HOME"/{cli,sockets,config}

# Set permissions
# UID 1000 = container user (plugin containers write to sockets)
echo "Setting permissions..."
chmod 755 "$CLAUDE_HOME"/cli
chmod 770 "$CLAUDE_HOME"/sockets
chmod 755 "$CLAUDE_HOME"/config

# Optionally set ownership for sockets directory
# Uncomment if your user ID is not 1000
# sudo chown 1000:1000 "$CLAUDE_HOME"/sockets

# Copy CLI wrappers
echo "Installing CLI wrappers..."
cp "$REPO_DIR"/cli/* "$CLAUDE_HOME"/cli/
chmod +x "$CLAUDE_HOME"/cli/*

# Copy default configs
echo "Installing default configurations..."
cp "$REPO_DIR"/config/* "$CLAUDE_HOME"/config/ 2>/dev/null || true

echo ""
echo "Installation complete!"
echo ""
echo "Directory structure:"
echo "  $CLAUDE_HOME/"
echo "  ├── cli/           # Plugin wrapper scripts"
echo "  ├── sockets/       # Plugin Unix sockets"
echo "  └── config/        # Plugin configuration"
echo ""
echo "Next steps:"
echo "  1. Set your GitHub token: export GITHUB_TOKEN=your_token"
echo "  2. Build containers: docker compose build"
echo "  3. Start Claude: ./scripts/run.sh"
echo ""
echo "To add a new plugin:"
echo "  1. Add wrapper:  cp my-tool $CLAUDE_HOME/cli/"
echo "  2. Add config:   cp my-tool.yaml $CLAUDE_HOME/config/"
echo "  3. Add service to docker-compose.yaml"
echo "  4. Start plugin: docker compose up -d my-tool-plugin"

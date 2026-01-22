#!/bin/bash

# Claude Container Aliases
# Source this file in your shell to get convenient aliases for claude-container scripts
#
# Usage:
#   source /path/to/claude-container/aliases.sh
#
# Or add to your ~/.bashrc or ~/.zshrc:
#   source /path/to/claude-container/aliases.sh

# Detect the directory where this script is located
CLAUDE_CONTAINER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Main aliases for running Claude Code
# Note: 'claude' may conflict with an existing claude CLI installation
# If you have conflicts, use the 'ccontainer' or 'cc' aliases instead
alias claude="$CLAUDE_CONTAINER_DIR/run.sh"
alias ccontainer="$CLAUDE_CONTAINER_DIR/run.sh"
alias cc="$CLAUDE_CONTAINER_DIR/run.sh"

# Aliases to show the current project's image name
alias claude-image="$CLAUDE_CONTAINER_DIR/image-name.sh"
alias ccontainer-image="$CLAUDE_CONTAINER_DIR/image-name.sh"
alias cc-image="$CLAUDE_CONTAINER_DIR/image-name.sh"

# Aliases to force rebuild the project image
alias claude-rebuild="$CLAUDE_CONTAINER_DIR/run.sh --rebuild"
alias ccontainer-rebuild="$CLAUDE_CONTAINER_DIR/run.sh --rebuild"
alias cc-rebuild="$CLAUDE_CONTAINER_DIR/run.sh --rebuild"

# Aliases for running with proxy (docker-compose)
alias claude-proxy="$CLAUDE_CONTAINER_DIR/run-with-proxy.sh"
alias cc-proxy="$CLAUDE_CONTAINER_DIR/run-with-proxy.sh"
alias claude-proxy-stop="$CLAUDE_CONTAINER_DIR/run-with-proxy.sh --stop"
alias claude-proxy-logs="$CLAUDE_CONTAINER_DIR/run-with-proxy.sh --logs"
alias claude-proxy-shell="$CLAUDE_CONTAINER_DIR/run-with-proxy.sh --shell"

# Export the directory for use in other scripts if needed
export CLAUDE_CONTAINER_DIR

# Print confirmation message
echo "Claude Container aliases loaded from: $CLAUDE_CONTAINER_DIR"
echo ""
echo "Available aliases:"
echo "  claude, ccontainer, cc       - Run Claude Code in container"
echo "  claude-image, cc-image       - Show project image name"
echo "  claude-rebuild, cc-rebuild   - Force rebuild project image"
echo ""
echo "Proxy aliases (docker-compose with service proxy):"
echo "  claude-proxy, cc-proxy       - Run with proxy container"
echo "  claude-proxy-stop            - Stop proxy containers"
echo "  claude-proxy-logs            - View proxy logs"
echo "  claude-proxy-shell           - Open shell in running container"
echo ""
echo "Note: 'claude' may override an existing claude CLI if installed."
echo "      Use 'ccontainer' or 'cc' for guaranteed non-conflicting aliases."

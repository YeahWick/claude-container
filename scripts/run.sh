#!/bin/bash
# Run script for Claude Container v2
#
# Starts the Claude container with all configured plugins.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude-container}"

# Export for docker compose
export CLAUDE_HOME
export PROJECT_DIR="${PROJECT_DIR:-$(pwd)}"

# Check if installed
if [ ! -d "$CLAUDE_HOME/cli" ]; then
    echo "Error: Claude Container not installed."
    echo "Run: ./scripts/install.sh"
    exit 1
fi

# Check for API key
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "Warning: ANTHROPIC_API_KEY not set"
    echo "Claude Code may not work without an API key."
    echo ""
fi

# Check for GitHub token
if [ -z "$GITHUB_TOKEN" ]; then
    echo "Note: GITHUB_TOKEN not set"
    echo "Git operations requiring authentication will fail."
    echo ""
fi

cd "$REPO_DIR"

# Parse arguments
ACTION="${1:-run}"

case "$ACTION" in
    run)
        # Start plugins first, then claude
        echo "Starting plugin containers..."
        docker compose up -d git-plugin

        # Wait for plugin sockets
        echo "Waiting for plugins..."
        sleep 2

        # Check if git socket is available
        if [ ! -S "$CLAUDE_HOME/sockets/git.sock" ]; then
            echo "Warning: git plugin socket not ready"
            echo "Check: docker compose logs git-plugin"
        fi

        # Start Claude interactively
        echo "Starting Claude..."
        docker compose run --rm claude
        ;;

    start)
        # Start all containers in background
        echo "Starting all containers..."
        docker compose up -d
        echo ""
        echo "Containers started. Use 'docker compose logs -f' to view logs."
        echo "To connect to Claude: docker compose exec claude bash"
        ;;

    stop)
        echo "Stopping all containers..."
        docker compose down
        ;;

    status)
        echo "Container status:"
        docker compose ps
        echo ""
        echo "Plugin sockets:"
        ls -la "$CLAUDE_HOME/sockets/" 2>/dev/null || echo "  (none)"
        ;;

    logs)
        docker compose logs -f "${2:-}"
        ;;

    build)
        echo "Building containers..."
        docker compose build
        ;;

    *)
        echo "Usage: $0 {run|start|stop|status|logs|build}"
        echo ""
        echo "Commands:"
        echo "  run    - Start plugins and run Claude interactively (default)"
        echo "  start  - Start all containers in background"
        echo "  stop   - Stop all containers"
        echo "  status - Show container and plugin status"
        echo "  logs   - View container logs (optionally specify service)"
        echo "  build  - Build container images"
        exit 1
        ;;
esac

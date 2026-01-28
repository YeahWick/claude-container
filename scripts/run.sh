#!/bin/bash
# Run script for Claude Container
#
# Starts the Claude client container with the tool server.
# Supports multiple concurrent instances via unique project names.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude-container}"

# Export for docker compose
export CLAUDE_HOME
export PROJECT_DIR="${PROJECT_DIR:-$(pwd)}"

# Generate instance ID from PROJECT_DIR hash for concurrent support
# Uses first 8 characters of md5sum for uniqueness
generate_instance_id() {
    local path="$1"
    # Normalize path and generate hash
    local normalized_path
    normalized_path="$(cd "$path" 2>/dev/null && pwd -P || echo "$path")"
    echo -n "$normalized_path" | md5sum | cut -c1-8
}

# Get or generate instance ID
if [ -z "$INSTANCE_ID" ]; then
    INSTANCE_ID="$(generate_instance_id "$PROJECT_DIR")"
fi
export INSTANCE_ID

# Set compose project name for container namespacing
# This ensures containers from different instances don't conflict
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-claude-$INSTANCE_ID}"

# Check if installed
if [ ! -d "$CLAUDE_HOME/tools/bin" ]; then
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
        # Show instance info
        echo "Instance: $INSTANCE_ID (from $PROJECT_DIR)"
        echo "Project:  $COMPOSE_PROJECT_NAME"
        echo ""

        # Start tool server first
        echo "Starting tool server..."
        docker compose up -d tool-server

        # Wait for tool server socket
        echo "Waiting for tool server..."
        SOCKET_FILE="$CLAUDE_HOME/sockets/tool-$INSTANCE_ID.sock"
        for i in {1..10}; do
            if [ -S "$SOCKET_FILE" ]; then
                break
            fi
            sleep 0.5
        done

        # Check if tool server socket is available
        if [ ! -S "$SOCKET_FILE" ]; then
            echo "Warning: Tool server socket not ready at $SOCKET_FILE"
            echo "Check: docker compose logs tool-server"
        fi

        # Start Claude client interactively
        echo "Starting Claude..."
        docker compose run --rm claude
        ;;

    start)
        # Show instance info
        echo "Instance: $INSTANCE_ID (from $PROJECT_DIR)"
        echo "Project:  $COMPOSE_PROJECT_NAME"
        echo ""

        # Start all containers in background
        echo "Starting all containers..."
        docker compose up -d
        echo ""
        echo "Containers started. Use 'docker compose logs -f' to view logs."
        echo "To connect to Claude: docker compose exec claude bash"
        echo "Socket: $CLAUDE_HOME/sockets/tool-$INSTANCE_ID.sock"
        ;;

    stop)
        echo "Instance: $INSTANCE_ID"
        echo "Project:  $COMPOSE_PROJECT_NAME"
        echo ""
        echo "Stopping all containers..."
        docker compose down

        # Clean up instance socket
        SOCKET_FILE="$CLAUDE_HOME/sockets/tool-$INSTANCE_ID.sock"
        if [ -S "$SOCKET_FILE" ]; then
            rm -f "$SOCKET_FILE"
            echo "Removed socket: $SOCKET_FILE"
        fi
        ;;

    status)
        echo "Instance: $INSTANCE_ID"
        echo "Project:  $COMPOSE_PROJECT_NAME"
        echo ""
        echo "Container status:"
        docker compose ps
        echo ""
        echo "Instance socket:"
        ls -la "$CLAUDE_HOME/sockets/tool-$INSTANCE_ID.sock" 2>/dev/null || echo "  (not found)"
        echo ""
        echo "All sockets:"
        ls -la "$CLAUDE_HOME/sockets/"*.sock 2>/dev/null || echo "  (none)"
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
        echo "  run    - Start tool server and run Claude interactively (default)"
        echo "  start  - Start all containers in background"
        echo "  stop   - Stop all containers"
        echo "  status - Show container status"
        echo "  logs   - View container logs (optionally specify service)"
        echo "  build  - Build container images"
        exit 1
        ;;
esac

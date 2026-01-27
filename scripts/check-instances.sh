#!/bin/bash
# Check running Claude Container instances
#
# Shows which instance IDs correspond to which project paths,
# and which containers are currently running.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude-container}"

# Generate instance ID from path (same algorithm as run.sh)
generate_instance_id() {
    local path="$1"
    local normalized_path
    normalized_path="$(cd "$path" 2>/dev/null && pwd -P || echo "$path")"
    echo -n "$normalized_path" | md5sum | cut -c1-8
}

# Get instance ID for a path
get_instance_for_path() {
    local path="$1"
    generate_instance_id "$path"
}

# List all running claude containers
list_running_instances() {
    echo "Running Claude Container instances:"
    echo "===================================="
    echo ""

    # Find all running containers with claude- prefix in project name
    local found=0
    while IFS= read -r line; do
        if [ -n "$line" ]; then
            found=1
            local container_name project_name instance_id
            container_name=$(echo "$line" | awk '{print $1}')
            # Extract project name (format: projectname-service-1)
            project_name=$(echo "$container_name" | sed 's/-claude-1$//' | sed 's/-tool-server-1$//')
            # Extract instance ID from project name (format: claude-{instance_id})
            instance_id=$(echo "$project_name" | sed 's/^claude-//')

            echo "  Container: $container_name"
            echo "  Instance:  $instance_id"
            echo "  Socket:    $CLAUDE_HOME/sockets/tool-$instance_id.sock"
            echo ""
        fi
    done < <(docker ps --filter "name=claude-" --format "{{.Names}}" 2>/dev/null | grep -E "claude-[a-f0-9]{8}-(claude|tool-server)-1" || true)

    if [ "$found" -eq 0 ]; then
        echo "  (no running instances)"
        echo ""
    fi
}

# List all sockets
list_sockets() {
    echo "Active sockets:"
    echo "==============="
    echo ""

    if [ -d "$CLAUDE_HOME/sockets" ]; then
        local found=0
        for sock in "$CLAUDE_HOME/sockets"/tool-*.sock; do
            if [ -S "$sock" ]; then
                found=1
                local instance_id
                instance_id=$(basename "$sock" | sed 's/^tool-//' | sed 's/\.sock$//')
                echo "  $sock"
                echo "    Instance: $instance_id"
                echo ""
            fi
        done
        if [ "$found" -eq 0 ]; then
            echo "  (no active sockets)"
            echo ""
        fi
    else
        echo "  (sockets directory not found)"
        echo ""
    fi
}

# Check what instance a path would use
check_path() {
    local path="$1"
    if [ -z "$path" ]; then
        path="$(pwd)"
    fi

    local instance_id
    instance_id=$(get_instance_for_path "$path")
    local normalized_path
    normalized_path="$(cd "$path" 2>/dev/null && pwd -P || echo "$path")"

    echo "Path mapping:"
    echo "============="
    echo ""
    echo "  Path:     $normalized_path"
    echo "  Instance: $instance_id"
    echo "  Project:  claude-$instance_id"
    echo "  Socket:   $CLAUDE_HOME/sockets/tool-$instance_id.sock"
    echo ""

    # Check if this instance is running
    if docker ps --filter "name=claude-$instance_id-" --format "{{.Names}}" 2>/dev/null | grep -q .; then
        echo "  Status: RUNNING"
    elif [ -S "$CLAUDE_HOME/sockets/tool-$instance_id.sock" ]; then
        echo "  Status: STALE (socket exists but containers not running)"
    else
        echo "  Status: NOT RUNNING"
    fi
    echo ""
}

# Main
case "${1:-}" in
    -h|--help)
        echo "Usage: $0 [path]"
        echo ""
        echo "With no arguments: List all running instances and sockets"
        echo "With path argument: Show what instance ID a path would use"
        echo ""
        echo "Examples:"
        echo "  $0                    # List all running instances"
        echo "  $0 /path/to/project   # Check instance for specific path"
        echo "  $0 .                   # Check instance for current directory"
        ;;
    "")
        list_running_instances
        list_sockets
        ;;
    *)
        check_path "$1"
        ;;
esac

#!/bin/bash
# Run Claude Code with Proxy
#
# This script starts both the Claude Code container and the proxy container
# using docker-compose, providing controlled access to external services.
#
# Usage:
#   ./run-with-proxy.sh [options]
#
# Options:
#   --build     Force rebuild of containers
#   --detach    Run in background
#   --stop      Stop running containers
#   --logs      Show proxy logs
#   --help      Show this help

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

print_info() {
    echo -e "${BLUE}$1${NC}"
}

print_success() {
    echo -e "${GREEN}$1${NC}"
}

print_warning() {
    echo -e "${YELLOW}$1${NC}"
}

print_error() {
    echo -e "${RED}$1${NC}" >&2
}

show_help() {
    cat << EOF
${CYAN}Claude Code with Proxy${NC}

Usage: $0 [options]

${YELLOW}Options:${NC}
  --build       Force rebuild of containers
  --detach, -d  Run containers in background
  --stop        Stop running containers
  --logs        Show proxy logs (follow mode)
  --status      Show container status
  --shell       Open shell in Claude Code container
  --help        Show this help

${YELLOW}Environment Variables:${NC}
  GITHUB_TOKEN         GitHub personal access token
  BLOCKED_BRANCHES     JSON array of blocked branches (default: ["main","master"])
  PROJECT_DIR          Directory to mount as workspace (default: current dir)
  ANTHROPIC_KEY_FILE   Path to Anthropic API key file (default: ~/.anthropic_key)

${YELLOW}Examples:${NC}
  $0                          # Start interactive session
  $0 --detach                 # Start in background
  $0 --shell                  # Open shell in running container
  PROJECT_DIR=/my/project $0  # Start with specific project

${YELLOW}Proxy Tools (available inside container):${NC}
  proxy-tools              # List available tools
  proxy-github help        # GitHub tool help
  proxy-github status      # Git status
  proxy-github push        # Push with branch protection
  proxy-github blocked     # Show protected branches

EOF
}

check_docker_compose() {
    if command -v docker-compose &> /dev/null; then
        COMPOSE_CMD="docker-compose"
    elif docker compose version &> /dev/null 2>&1; then
        COMPOSE_CMD="docker compose"
    else
        print_error "Docker Compose not found. Please install Docker Compose."
        exit 1
    fi
}

# Check for required files
check_requirements() {
    if [ ! -f "$HOME/.anthropic_key" ] && [ -z "${ANTHROPIC_API_KEY:-}" ]; then
        print_warning "Warning: No Anthropic API key found."
        echo "Create ~/.anthropic_key with your API key or set ANTHROPIC_API_KEY environment variable."
    fi

    if [ -z "${GITHUB_TOKEN:-}" ] && [ ! -f ".env" ]; then
        print_warning "Warning: No GitHub token configured."
        echo "Set GITHUB_TOKEN environment variable or create a .env file."
        echo "See .env.example for configuration options."
    fi
}

start_containers() {
    local build_flag=""
    local detach_flag=""

    [ "$1" = "--build" ] && build_flag="--build"
    [ "$2" = "--detach" ] || [ "$2" = "-d" ] && detach_flag="-d"

    print_info "Starting Claude Code with Proxy..."

    # Set default PROJECT_DIR if not set
    export PROJECT_DIR="${PROJECT_DIR:-$(pwd)}"

    if [ -n "$build_flag" ]; then
        print_info "Building containers..."
    fi

    if [ -n "$detach_flag" ]; then
        $COMPOSE_CMD up $build_flag $detach_flag
        print_success "Containers started in background."
        echo
        echo "Use '$0 --shell' to open a shell in the Claude Code container."
        echo "Use '$0 --logs' to view proxy logs."
        echo "Use '$0 --stop' to stop containers."
    else
        # Interactive mode
        print_info "Starting interactive session..."
        print_info "Proxy tools available: proxy-tools, proxy-github"
        echo
        $COMPOSE_CMD up $build_flag
    fi
}

stop_containers() {
    print_info "Stopping containers..."
    $COMPOSE_CMD down
    print_success "Containers stopped."
}

show_logs() {
    print_info "Showing proxy logs (Ctrl+C to exit)..."
    $COMPOSE_CMD logs -f proxy
}

show_status() {
    print_info "Container status:"
    $COMPOSE_CMD ps
}

open_shell() {
    print_info "Opening shell in Claude Code container..."
    $COMPOSE_CMD exec claude bash
}

main() {
    check_docker_compose

    case "${1:-}" in
        --help|-h)
            show_help
            ;;
        --stop)
            stop_containers
            ;;
        --logs)
            show_logs
            ;;
        --status)
            show_status
            ;;
        --shell)
            open_shell
            ;;
        --build)
            check_requirements
            start_containers "--build" "$2"
            ;;
        --detach|-d)
            check_requirements
            start_containers "" "--detach"
            ;;
        "")
            check_requirements
            start_containers
            ;;
        *)
            print_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
}

main "$@"

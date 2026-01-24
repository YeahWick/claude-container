#!/bin/bash
# Run Claude Code with Proxy
#
# This script starts both the Claude Code container and the proxy container
# using podman-compose (or docker-compose as fallback), providing controlled
# access to external services.
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
  GITHUB_TOKEN           GitHub personal access token
  PROJECT_DIR            Directory to mount as workspace (default: current dir)
  ANTHROPIC_KEY_FILE     Path to Anthropic API key file (default: ~/.anthropic_key)
  PROXY_AUTH_SECRET      Shared secret for proxy auth (auto-generated if not set)
  PROXY_GITHUB_BLOCKED_BRANCHES      JSON array of blocked branches
  PROXY_GITHUB_ALLOWED_BRANCH_PATTERNS  JSON array of allowed patterns

${YELLOW}Security:${NC}
  The proxy runs on an internal Podman network, accessible only from the
  Claude Code container. Optional shared-secret authentication adds an
  additional layer of security. If PROXY_AUTH_SECRET is not set, one will
  be auto-generated for the session.

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

# Detect container runtime and compose command
detect_compose() {
    # Check for Podman first (preferred)
    if command -v podman &> /dev/null; then
        CONTAINER_CMD="podman"
        # Check for podman-compose or podman compose
        if command -v podman-compose &> /dev/null; then
            COMPOSE_CMD="podman-compose"
            print_info "Using podman-compose"
        elif podman compose version &> /dev/null 2>&1; then
            COMPOSE_CMD="podman compose"
            print_info "Using podman compose"
        else
            print_error "Podman found but podman-compose is not installed."
            echo "Install with: pip install podman-compose"
            echo "Or: sudo dnf install podman-compose (Fedora)"
            echo "Or: brew install podman-compose (macOS)"
            exit 1
        fi
    # Fall back to Docker
    elif command -v docker &> /dev/null; then
        CONTAINER_CMD="docker"
        if command -v docker-compose &> /dev/null; then
            COMPOSE_CMD="docker-compose"
            print_info "Using docker-compose"
        elif docker compose version &> /dev/null 2>&1; then
            COMPOSE_CMD="docker compose"
            print_info "Using docker compose"
        else
            print_error "Docker found but docker-compose is not available."
            exit 1
        fi
    else
        print_error "Neither Podman nor Docker found. Please install Podman."
        echo "Install with:"
        echo "  macOS:  brew install podman podman-compose"
        echo "  Fedora: sudo dnf install podman podman-compose"
        echo "  Ubuntu: sudo apt install podman python3-pip && pip install podman-compose"
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

    # For Podman, ensure the machine is running (macOS/Windows)
    if [ "$CONTAINER_CMD" = "podman" ]; then
        if ! podman info &> /dev/null; then
            print_warning "Podman machine may not be running."
            echo "Start it with: podman machine start"
        fi
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

    # Auto-generate auth secret if not set
    if [ -z "${PROXY_AUTH_SECRET:-}" ]; then
        if command -v openssl &> /dev/null; then
            export PROXY_AUTH_SECRET=$(openssl rand -hex 32)
            print_info "Generated session auth secret"
        else
            print_warning "Warning: openssl not found, skipping auth secret generation"
            print_warning "Set PROXY_AUTH_SECRET manually for authentication"
        fi
    else
        print_info "Using configured auth secret"
    fi

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
    detect_compose

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

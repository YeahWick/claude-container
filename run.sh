#!/bin/bash
# Claude Code Container Launcher
# Runs Claude Code with command-agent for secure git/gh operations

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Detect compose command
detect_compose() {
    if command -v podman-compose &>/dev/null; then
        echo "podman-compose"
    elif podman compose version &>/dev/null 2>&1; then
        echo "podman compose"
    elif command -v docker-compose &>/dev/null; then
        echo "docker-compose"
    elif docker compose version &>/dev/null 2>&1; then
        echo "docker compose"
    else
        echo ""
    fi
}

COMPOSE=$(detect_compose)

if [ -z "$COMPOSE" ]; then
    echo -e "${RED}Error: No container compose tool found${NC}"
    echo "Install podman-compose: pip install podman-compose"
    exit 1
fi

show_help() {
    cat << EOF
Claude Code Container

Usage: $0 [command] [options]

Commands:
  (none)      Start interactive Claude Code session
  --build     Force rebuild containers
  --stop      Stop containers
  --shell     Open shell in running container
  --logs      Show command-agent logs
  --status    Show container status
  --help      Show this help

Environment:
  GITHUB_TOKEN              GitHub personal access token
  PROJECT_DIR               Project directory to mount (default: .)
  ANTHROPIC_KEY_FILE        Path to API key file (default: ~/.anthropic_key)
  BLOCKED_BRANCHES          JSON array of protected branches (default: ["main","master"])
  ALLOWED_BRANCH_PATTERNS   JSON array of allowed patterns (default: [])

EOF
}

case "${1:-}" in
    --help|-h)
        show_help
        ;;
    --stop)
        echo -e "${YELLOW}Stopping containers...${NC}"
        $COMPOSE down
        ;;
    --logs)
        $COMPOSE logs -f command-agent
        ;;
    --status)
        $COMPOSE ps
        ;;
    --shell)
        $COMPOSE exec claude bash
        ;;
    --build)
        echo -e "${GREEN}Building and starting...${NC}"
        export PROJECT_DIR="${PROJECT_DIR:-$(pwd)}"
        $COMPOSE up --build
        ;;
    "")
        # Check requirements
        if [ ! -f "${ANTHROPIC_KEY_FILE:-$HOME/.anthropic_key}" ]; then
            echo -e "${YELLOW}Warning: No Anthropic API key found at ${ANTHROPIC_KEY_FILE:-~/.anthropic_key}${NC}"
        fi
        if [ -z "${GITHUB_TOKEN:-}" ]; then
            echo -e "${YELLOW}Warning: GITHUB_TOKEN not set - git push/pull won't work${NC}"
        fi

        echo -e "${GREEN}Starting Claude Code...${NC}"
        export PROJECT_DIR="${PROJECT_DIR:-$(pwd)}"
        $COMPOSE up
        ;;
    *)
        echo -e "${RED}Unknown command: $1${NC}"
        show_help
        exit 1
        ;;
esac

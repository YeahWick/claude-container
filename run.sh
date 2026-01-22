#!/bin/bash

# Claude Code Container Launcher
# Run this script from your project directory to start Claude Code in a container

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_NAME="claude-code"
KEY_FILE="$HOME/.anthropic_key"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Check if container tool is available
if ! command -v container &> /dev/null; then
    echo -e "${RED}Error: Apple container tool not found${NC}"
    echo "Install from: https://github.com/apple/container/releases"
    exit 1
fi

# Check if image exists, build if not
if ! container images ls 2>/dev/null | grep -q "$IMAGE_NAME"; then
    echo -e "${YELLOW}Image '$IMAGE_NAME' not found. Building...${NC}"
    container build -t "$IMAGE_NAME" "$SCRIPT_DIR"
fi

# Check for API key file
if [ ! -f "$KEY_FILE" ]; then
    echo -e "${RED}Error: API key file not found at $KEY_FILE${NC}"
    echo "Create it with: echo 'your_api_key' > ~/.anthropic_key"
    exit 1
fi

echo -e "${GREEN}Starting Claude Code container...${NC}"
echo -e "${GREEN}Workspace:${NC} $(pwd)"
echo ""

# Run container with mounts:
# - Current directory -> /home/claude/workspace
# - API key file -> /home/claude/.anthropic_key (read-only)
exec container run -it \
    -v "$(pwd):/home/claude/workspace" \
    -v "$KEY_FILE:/home/claude/.anthropic_key:ro" \
    "$IMAGE_NAME" "$@"

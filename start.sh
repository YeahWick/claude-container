#!/bin/bash

# Claude Code Container Startup Script
# This script initializes the environment and launches Claude Code

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   Claude Code Container Session${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Load API key from file if not set via environment
KEY_FILE="$HOME/.anthropic_key"
if [ -z "$ANTHROPIC_API_KEY" ] && [ -f "$KEY_FILE" ]; then
    export ANTHROPIC_API_KEY="$(cat "$KEY_FILE")"
fi

# Check for API key
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo -e "${YELLOW}Warning: ANTHROPIC_API_KEY is not set${NC}"
    echo -e "${YELLOW}Mount your key file or set -e ANTHROPIC_API_KEY=your_key${NC}"
    echo ""
fi

# Show current workspace
echo -e "${GREEN}Workspace:${NC} $(pwd)"
if [ -d ".git" ]; then
    echo -e "${GREEN}Git repo:${NC} $(git remote get-url origin 2>/dev/null || echo 'local repo')"
    echo -e "${GREEN}Branch:${NC} $(git branch --show-current 2>/dev/null || echo 'unknown')"
fi
echo ""

# Launch Claude Code with any passed arguments
# If no arguments provided, start in interactive mode
if [ $# -eq 0 ]; then
    echo -e "${GREEN}Starting Claude Code in interactive mode...${NC}"
    echo ""
    exec claude
else
    echo -e "${GREEN}Running Claude Code with arguments...${NC}"
    echo ""
    exec claude "$@"
fi

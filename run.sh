#!/bin/bash

# Claude Code Container Launcher
# Run this script from your project directory to start Claude Code in a container

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_IMAGE="claude-code"
KEY_FILE="$HOME/.anthropic_key"
PROJECT_SETUP=".claude-container/setup.sh"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Check if container tool is available
if ! command -v container &> /dev/null; then
    echo -e "${RED}Error: Apple container tool not found${NC}"
    echo "Install from: https://github.com/apple/container/releases"
    exit 1
fi

# Ensure base image exists
if ! container images ls 2>/dev/null | grep -q "$BASE_IMAGE"; then
    echo -e "${YELLOW}Base image '$BASE_IMAGE' not found. Building...${NC}"
    container build -t "$BASE_IMAGE" "$SCRIPT_DIR"
fi

# Check for API key file
if [ ! -f "$KEY_FILE" ]; then
    echo -e "${RED}Error: API key file not found at $KEY_FILE${NC}"
    echo "Create it with: echo 'your_api_key' > ~/.anthropic_key"
    exit 1
fi

# Determine which image to use
IMAGE_NAME="$BASE_IMAGE"

# Check if project has a custom setup script
if [ -f "$PROJECT_SETUP" ]; then
    # Generate a unique image name based on the project directory
    PROJECT_NAME=$(basename "$(pwd)" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g')
    PROJECT_IMAGE="claude-code-${PROJECT_NAME}"

    # Calculate checksum of setup script to detect changes
    SETUP_CHECKSUM=$(sha256sum "$PROJECT_SETUP" | cut -c1-12)
    PROJECT_IMAGE_TAG="${PROJECT_IMAGE}:${SETUP_CHECKSUM}"

    # Check if project-specific image with this checksum exists
    if ! container images ls 2>/dev/null | grep -q "$PROJECT_IMAGE.*$SETUP_CHECKSUM"; then
        echo -e "${BLUE}Project setup script detected: $PROJECT_SETUP${NC}"
        echo -e "${YELLOW}Building project-specific image...${NC}"

        # Create a temporary build context
        BUILD_DIR=$(mktemp -d)
        trap "rm -rf $BUILD_DIR" EXIT

        # Copy the setup script
        cp "$PROJECT_SETUP" "$BUILD_DIR/setup.sh"

        # Generate a Containerfile that extends the base image
        cat > "$BUILD_DIR/Containerfile" <<EOF
FROM $BASE_IMAGE

# Copy and run project-specific setup
USER root
COPY setup.sh /tmp/project-setup.sh
RUN chmod +x /tmp/project-setup.sh && /tmp/project-setup.sh && rm /tmp/project-setup.sh

# Switch back to claude user
USER claude
WORKDIR /home/claude/workspace
ENTRYPOINT ["/home/claude/start.sh"]
EOF

        # Build the project-specific image
        container build -t "$PROJECT_IMAGE_TAG" "$BUILD_DIR"
        echo -e "${GREEN}Project image built successfully!${NC}"
    else
        echo -e "${GREEN}Using cached project image${NC}"
    fi

    IMAGE_NAME="$PROJECT_IMAGE_TAG"
fi

echo -e "${GREEN}Starting Claude Code container...${NC}"
echo -e "${GREEN}Image:${NC} $IMAGE_NAME"
echo -e "${GREEN}Workspace:${NC} $(pwd)"
echo ""

# Run container with mounts:
# - Current directory -> /home/claude/workspace
# - API key file -> /home/claude/.anthropic_key (read-only)
exec container run -it \
    -v "$(pwd):/home/claude/workspace" \
    -v "$KEY_FILE:/home/claude/.anthropic_key:ro" \
    "$IMAGE_NAME" "$@"

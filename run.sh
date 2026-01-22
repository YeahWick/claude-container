#!/bin/bash

# Claude Code Container Launcher
# Run this script from your project directory to start Claude Code in a container

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_IMAGE="claude-code"
KEY_FILE="$HOME/.anthropic_key"
PROJECT_DIR=".claude-container"
FORCE_REBUILD=false

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Parse arguments
CLAUDE_ARGS=()
while [[ $# -gt 0 ]]; do
    case $1 in
        --rebuild)
            FORCE_REBUILD=true
            shift
            ;;
        *)
            CLAUDE_ARGS+=("$1")
            shift
            ;;
    esac
done

# Check if container tool is available
if ! command -v container &> /dev/null; then
    echo -e "${RED}Error: Apple container tool not found${NC}"
    echo "Install from: https://github.com/apple/container/releases"
    exit 1
fi

# Ensure base image exists
if ! container images ls 2>/dev/null | grep -q "^$BASE_IMAGE[[:space:]]"; then
    echo -e "${YELLOW}Base image '$BASE_IMAGE' not found. Building...${NC}"
    container build -t "$BASE_IMAGE" "$SCRIPT_DIR"
fi

# Check for API key file
if [ ! -f "$KEY_FILE" ]; then
    echo -e "${RED}Error: API key file not found at $KEY_FILE${NC}"
    echo "Create it with: echo 'your_api_key' > ~/.anthropic_key"
    exit 1
fi

# Calculate checksum of project setup files
calculate_checksum() {
    local checksum_input=""

    # Include setup.sh if it exists
    if [ -f "$PROJECT_DIR/setup.sh" ]; then
        checksum_input+=$(cat "$PROJECT_DIR/setup.sh")
    fi

    # Include custom Containerfile if it exists
    if [ -f "$PROJECT_DIR/Containerfile" ]; then
        checksum_input+=$(cat "$PROJECT_DIR/Containerfile")
    fi

    # Include common dependency files in checksum (if they exist)
    for dep_file in package.json requirements.txt Gemfile go.mod Cargo.toml; do
        if [ -f "$dep_file" ]; then
            checksum_input+=$(cat "$dep_file")
        fi
    done

    echo -n "$checksum_input" | sha256sum | cut -c1-12
}

# Remove old images for this project
cleanup_old_images() {
    local project_image="$1"
    local current_tag="$2"

    # List all tags for this project image and remove old ones
    container images ls 2>/dev/null | grep "^${project_image}:" | while read -r line; do
        local tag=$(echo "$line" | awk '{print $1":"$2}')
        if [ "$tag" != "$current_tag" ]; then
            echo -e "${YELLOW}Removing old image: $tag${NC}"
            container images rm "$tag" 2>/dev/null || true
        fi
    done
}

# Determine which image to use
IMAGE_NAME="$BASE_IMAGE"

# Check if project has custom setup
if [ -d "$PROJECT_DIR" ] && { [ -f "$PROJECT_DIR/setup.sh" ] || [ -f "$PROJECT_DIR/Containerfile" ]; }; then
    # Generate a unique image name based on the project directory
    PROJECT_NAME=$(basename "$(pwd)" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g')
    PROJECT_IMAGE="claude-code-${PROJECT_NAME}"

    # Calculate checksum of all setup files
    SETUP_CHECKSUM=$(calculate_checksum)
    PROJECT_IMAGE_TAG="${PROJECT_IMAGE}:${SETUP_CHECKSUM}"

    # Check if we need to build
    NEEDS_BUILD=false
    if [ "$FORCE_REBUILD" = true ]; then
        echo -e "${YELLOW}Force rebuild requested${NC}"
        NEEDS_BUILD=true
    elif ! container images ls 2>/dev/null | grep -q "${PROJECT_IMAGE}.*${SETUP_CHECKSUM}"; then
        NEEDS_BUILD=true
    fi

    if [ "$NEEDS_BUILD" = true ]; then
        echo -e "${BLUE}Project setup detected in $PROJECT_DIR/${NC}"
        echo -e "${YELLOW}Building project-specific image...${NC}"

        # Clean up old images for this project
        cleanup_old_images "$PROJECT_IMAGE" "$PROJECT_IMAGE_TAG"

        # Check if using custom Containerfile or generating one
        if [ -f "$PROJECT_DIR/Containerfile" ]; then
            echo -e "${BLUE}Using custom Containerfile${NC}"
            container build -t "$PROJECT_IMAGE_TAG" -f "$PROJECT_DIR/Containerfile" .
        else
            # Generate and pipe Containerfile via stdin - no temp files needed
            container build -t "$PROJECT_IMAGE_TAG" -f - . <<EOF
FROM $BASE_IMAGE

# Copy and run project-specific setup
USER root
COPY $PROJECT_DIR/setup.sh /tmp/project-setup.sh
RUN chmod +x /tmp/project-setup.sh && /tmp/project-setup.sh && rm /tmp/project-setup.sh

# Switch back to claude user
USER claude
WORKDIR /home/claude/workspace
ENTRYPOINT ["/home/claude/start.sh"]
EOF
        fi
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
    "$IMAGE_NAME" "${CLAUDE_ARGS[@]}"

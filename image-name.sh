#!/bin/bash

# Show the image name that would be used for the current project

PROJECT_DIR=".claude-container"
BASE_IMAGE="claude-code"

# Calculate checksum of project setup files (same logic as run.sh)
calculate_checksum() {
    local checksum_input=""

    if [ -f "$PROJECT_DIR/setup.sh" ]; then
        checksum_input+=$(cat "$PROJECT_DIR/setup.sh")
    fi

    if [ -f "$PROJECT_DIR/Containerfile" ]; then
        checksum_input+=$(cat "$PROJECT_DIR/Containerfile")
    fi

    for dep_file in package.json requirements.txt Gemfile go.mod Cargo.toml; do
        if [ -f "$dep_file" ]; then
            checksum_input+=$(cat "$dep_file")
        fi
    done

    echo -n "$checksum_input" | sha256sum | cut -c1-12
}

# Check if project has custom setup
if [ -d "$PROJECT_DIR" ] && { [ -f "$PROJECT_DIR/setup.sh" ] || [ -f "$PROJECT_DIR/Containerfile" ]; }; then
    PROJECT_NAME=$(basename "$(pwd)" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g')
    PATH_HASH=$(echo -n "$(pwd)" | sha256sum | cut -c1-8)
    SETUP_CHECKSUM=$(calculate_checksum)

    echo "claude-code-${PROJECT_NAME}-${PATH_HASH}:${SETUP_CHECKSUM}"
else
    echo "$BASE_IMAGE"
fi

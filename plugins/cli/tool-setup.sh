#!/bin/bash
# Tool Setup Script
#
# Runs when the tool container starts to initialize the environment.
# Add tool-specific initialization here.

set -e

echo "=== Tool Container Setup ==="

# Create necessary directories
mkdir -p /run/plugins
mkdir -p /workspace

# Git configuration (if git is available)
if command -v git &> /dev/null; then
    echo "Configuring git..."
    # Safe directory configuration for workspace
    git config --global --add safe.directory /workspace
    git config --global --add safe.directory '*'

    # Default git settings for better UX
    git config --global init.defaultBranch main
    git config --global core.autocrlf input
    git config --global pull.rebase false

    echo "Git configured"
fi

# Tool-specific setup hooks
# Add custom initialization scripts in /app/setup.d/
SETUP_DIR="/app/setup.d"
if [ -d "$SETUP_DIR" ]; then
    echo "Running setup hooks from $SETUP_DIR..."
    for script in "$SETUP_DIR"/*.sh; do
        if [ -f "$script" ] && [ -x "$script" ]; then
            echo "Running: $script"
            "$script"
        fi
    done
fi

# Environment validation
echo "Validating environment..."

# Check socket directory is writable
if [ -w "/run/plugins" ]; then
    echo "  Socket directory: OK"
else
    echo "  Socket directory: WARNING - not writable"
fi

# Check workspace exists
if [ -d "/workspace" ]; then
    echo "  Workspace: OK"
else
    echo "  Workspace: WARNING - does not exist"
fi

# Load custom environment variables if present
ENV_FILE="/app/tool-env.sh"
if [ -f "$ENV_FILE" ]; then
    echo "Loading custom environment from $ENV_FILE"
    source "$ENV_FILE"
fi

echo "=== Setup Complete ==="
echo ""

# Execute the main command (typically the server)
exec "$@"

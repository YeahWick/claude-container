#!/bin/bash
# Example Client Setup Script
#
# This script runs in the Claude (client) container at startup.
# Use it for client-side configuration that doesn't require build tools.
#
# The script runs inside the Claude container with access to:
# - /workspace (your project directory, mounted from host)
# - Claude Code CLI and tool-client wrappers
#
# Common uses:
# - Setting up shell aliases
# - Configuring environment variables
# - Creating workspace directories

set -e

echo "Running client setup..."

# Example: Create a project-specific cache directory
mkdir -p /workspace/.cache

# Example: Set up any client-side configuration
# export MY_VAR="value"

echo "Client setup complete!"

#!/bin/bash
# Example Project Setup Script
#
# Place this file at: your-project/.claude-container/setup.sh
#
# This script runs when the Claude container starts, BEFORE Claude begins working.
# Use it to install project dependencies so Claude can build, test, and run your project.
#
# The script runs inside the tool-server container with access to:
# - /workspace (your project directory, mounted from host)
# - Tools like npm, pip, go, cargo (if installed in tool-server)
# - Network access for downloading dependencies
#
# Environment variables available:
# - TOOLS_DIR: Path to tools definitions
# - GITHUB_TOKEN / GH_TOKEN: For authenticated git operations

set -e

echo "Setting up project dependencies..."

# Detect project type and install dependencies
if [ -f "package.json" ]; then
    echo "Node.js project detected"
    if [ -f "package-lock.json" ]; then
        npm ci
    elif [ -f "yarn.lock" ]; then
        yarn install --frozen-lockfile
    else
        npm install
    fi
fi

if [ -f "requirements.txt" ]; then
    echo "Python project detected"
    pip install -r requirements.txt
fi

if [ -f "go.mod" ]; then
    echo "Go project detected"
    go mod download
fi

if [ -f "Cargo.toml" ]; then
    echo "Rust project detected"
    cargo fetch
fi

if [ -f "Gemfile" ]; then
    echo "Ruby project detected"
    bundle install
fi

echo "Project setup complete!"

#!/bin/bash
# Project-specific setup script for Claude Code container
# This script runs ONCE during image build, not on every container start
# Place this file at: .claude-container/setup.sh in your project root

set -e

echo "Installing project dependencies..."

# ==============================================================================
# SYSTEM PACKAGES
# ==============================================================================
# Install any system-level dependencies your project needs
# The script runs as root, so no sudo needed

apt-get update

# Example: Python development
# apt-get install -y python3 python3-pip python3-venv

# Example: Go development
# apt-get install -y golang-go

# Example: Rust development
# curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y

# Example: Java development
# apt-get install -y openjdk-21-jdk maven

# Example: Common build tools
# apt-get install -y build-essential cmake

# Clean up apt cache to reduce image size
apt-get clean
rm -rf /var/lib/apt/lists/*

# ==============================================================================
# GLOBAL TOOLS
# ==============================================================================
# Install global npm packages, pip packages, etc.

# Example: TypeScript and common tools
# npm install -g typescript ts-node prettier eslint

# Example: Python tools
# pip3 install --break-system-packages black flake8 pytest

# ==============================================================================
# CUSTOM SETUP
# ==============================================================================
# Add any other setup your project needs

echo "Project setup complete!"

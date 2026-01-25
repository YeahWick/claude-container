#!/bin/bash
# npm setup - runs at container start

command -v npm &>/dev/null || exit 0

# Set cache directory within workspace
npm config set cache /workspace/.npm-cache

# Disable update notifier
npm config set update-notifier false

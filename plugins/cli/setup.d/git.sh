#!/bin/bash
# Git setup - runs at container start

command -v git &>/dev/null || exit 0

# Mark workspace as safe directory
git config --global --add safe.directory /workspace
git config --global --add safe.directory '*'

# Defaults
git config --global init.defaultBranch main
git config --global pull.rebase false

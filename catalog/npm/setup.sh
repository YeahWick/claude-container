#!/bin/bash
# NPM setup - configure cache location
npm config set cache /workspace/.npm-cache 2>/dev/null || true
npm config set update-notifier false 2>/dev/null || true

#!/bin/bash
# npm restriction wrapper - blocks publishing

set -e

case "$1" in
    publish|unpublish|deprecate)
        echo "Error: npm $1 is not allowed" >&2
        exit 1
        ;;
    adduser|login|logout)
        echo "Error: npm authentication commands are not allowed" >&2
        exit 1
        ;;
esac

exec "$TOOL_BINARY" "$@"

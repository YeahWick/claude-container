#!/bin/bash
# NPM restrictions - block publishing and auth commands
case "$1" in
    publish|unpublish|deprecate|adduser|login|logout|token|owner|team|access)
        echo "Error: npm $1 is not allowed in this environment" >&2
        exit 1
        ;;
esac
exec "$TOOL_BINARY" "$@"

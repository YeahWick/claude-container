#!/bin/bash
# Claude Container Entrypoint (Client)
#
# Tool symlinks are pre-generated on the host by install.sh.
# The tools/ directory (containing bin/ and tools.d/) is mounted read-only.
# No runtime symlink generation or background polling needed.

set -e

# Execute the main command
exec "$@"

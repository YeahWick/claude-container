#!/usr/bin/env python3
"""Git plugin entry point.

Starts the git plugin socket server with configuration
loaded from /etc/plugins/git.yaml.
"""

import logging
import os
import sys
from pathlib import Path

import yaml

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from git import GitPlugin


def load_config(config_path: str) -> dict:
    """Load plugin configuration from YAML file.

    Args:
        config_path: Path to configuration file

    Returns:
        Configuration dictionary
    """
    path = Path(config_path)
    if not path.exists():
        logging.warning(f"Config file not found: {config_path}, using defaults")
        return {}

    with open(path) as f:
        config = yaml.safe_load(f) or {}

    # Substitute environment variables in string values
    def substitute_env(obj):
        if isinstance(obj, str):
            if obj.startswith('${') and obj.endswith('}'):
                var_name = obj[2:-1]
                return os.environ.get(var_name, '')
            return obj
        elif isinstance(obj, dict):
            return {k: substitute_env(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [substitute_env(v) for v in obj]
        return obj

    return substitute_env(config)


def main():
    """Main entry point for git plugin."""
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    )

    # Configuration paths
    socket_path = os.environ.get('PLUGIN_SOCKET', '/run/plugins/git.sock')
    config_path = os.environ.get('PLUGIN_CONFIG', '/etc/plugins/git.yaml')

    # Load configuration
    config = load_config(config_path)

    # Create plugin server
    plugin = GitPlugin(socket_path, config)

    # Load credentials from environment
    credential_vars = ['GITHUB_TOKEN', 'GH_TOKEN', 'GIT_TOKEN']
    plugin.load_credentials(credential_vars, clear_env=True)

    # Start server
    logging.info(f"Starting git plugin on {socket_path}")
    try:
        plugin.start()
    except KeyboardInterrupt:
        logging.info("Shutting down...")
    except Exception as e:
        logging.exception(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()

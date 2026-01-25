# Claude Container v2 - Plugin Socket System

A plugin-based architecture for the Claude Container where tools communicate via Unix domain sockets.

## Key Changes from v1

| Aspect | v1 | v2 |
|--------|----|----|
| Architecture | Monolithic command-agent | Independent tool plugins |
| Sockets | Single shared socket | One socket per tool |
| Configuration | Central .env file | Per-plugin YAML configs |
| Deployment | All-or-nothing | Independent plugin updates |
| Extensibility | Modify server.py | Add new plugin folder |

## Quick Start

```bash
# Start the system
./scripts/run.sh start

# Check status
./scripts/run.sh status

# Add a new plugin
./scripts/add-plugin.sh npm
```

## Documentation

- [SPEC.md](./SPEC.md) - Full technical specification
- [plugins/README.md](./plugins/README.md) - How to create plugins

## Architecture

```
Claude Container          Plugin Containers
┌─────────────┐          ┌─────────────────┐
│ git wrapper │────────► │ git.sock → git  │
│ gh wrapper  │────────► │ gh.sock  → gh   │
│ curl wrapper│────────► │ curl.sock→ curl │
└─────────────┘          └─────────────────┘
```

Each tool plugin:
- Listens on its own Unix socket
- Loads its own configuration
- Enforces its own rules
- Manages its own credentials

## Status

**MVP** - Implementing core functionality

- [ ] Base plugin library
- [ ] Git plugin
- [ ] Plugin client (wrapper scripts)
- [ ] Docker compose setup

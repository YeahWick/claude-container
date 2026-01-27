# Docker Bind Mounts for Binary Merging & UX Improvements

## Question

Can Docker use bind mounts to merge binaries into a folder — allowing repos to
provide their own restriction wrappers that get picked up at runtime? What other
Docker features could improve the user experience?

## Short Answer

Yes. Docker bind mounts can inject repo-provided files into the container at
runtime. The project already uses bind mounts extensively (`tools.d/`,
`client/`, `sockets/`). The main challenge is that Docker bind mounts are
**one-to-one**: you can mount `/host/path` to `/container/path`, but you can't
natively overlay two host directories onto the same container path. There are
several practical patterns to work around this.

---

## 1. Bind Mounts for Repo-Provided Restriction Wrappers

### The Goal

A project repo ships its own tool restrictions:

```
my-project/
├── .claude-container/
│   └── tools.d/
│       └── git/
│           └── restricted.sh    # "no force push in this repo"
├── src/
└── ...
```

When Claude Container runs against `my-project/`, those repo-level restrictions
are picked up automatically — merging with (or overriding) the global
`~/.claude-container/tools.d/` definitions.

### Pattern A: Dual Mount with Entrypoint Merge

Mount the repo's `.claude-container/` directory separately and merge at startup.

```yaml
# docker-compose.yaml
services:
  tool-server:
    volumes:
      # Global tools (from install)
      - ${CLAUDE_HOME}/tools.d:/app/tools.d:ro
      # Repo-local overrides (from the project directory)
      - ${PROJECT_DIR}/.claude-container/tools.d:/app/tools.d.project:ro
      # Merged output (writable tmpfs)
      - type: tmpfs
        target: /app/tools.d.merged
    environment:
      - TOOLS_DIR=/app/tools.d.merged
```

The entrypoint script merges the two:

```bash
# tool-setup.sh (entrypoint addition)
merge_tool_dirs() {
    local global="/app/tools.d"
    local project="/app/tools.d.project"
    local merged="/app/tools.d.merged"

    # Start with global tools
    cp -r "$global"/* "$merged"/ 2>/dev/null || true

    # Overlay project-specific files (overrides globals)
    if [ -d "$project" ]; then
        cp -r "$project"/* "$merged"/ 2>/dev/null || true
    fi
}
merge_tool_dirs
```

**Pros:**
- Simple, no special Docker features needed
- Clear precedence: project overrides global
- Works with existing tool discovery (just change `TOOLS_DIR`)

**Cons:**
- Requires a copy step at startup (trivial for small config files)
- Changes to source dirs after startup aren't reflected (unless re-merged)

### Pattern B: Symlink Forest

Mount both directories and create a symlink forest that combines them.

```bash
# Creates /app/tools.d.merged/{tool} → whichever source has it
for dir in /app/tools.d/*/; do
    tool="$(basename "$dir")"
    ln -s "$dir" "/app/tools.d.merged/$tool"
done

# Project overrides (replaces symlinks for tools that exist in both)
for dir in /app/tools.d.project/*/; do
    tool="$(basename "$dir")"
    ln -sf "$dir" "/app/tools.d.merged/$tool"
done
```

**Pros:**
- No file copying; changes to source dirs are reflected immediately
- Clear which source "wins" for each tool

**Cons:**
- Symlink resolution can be confusing to debug
- Individual files within a tool dir can't be selectively overridden (it's
  all-or-nothing per tool)

### Pattern C: OverlayFS (Linux-only, requires privileges)

Use OverlayFS to layer the project directory on top of the global one.

```bash
mount -t overlay overlay \
    -o lowerdir=/app/tools.d,upperdir=/app/tools.d.project,workdir=/tmp/overlay-work \
    /app/tools.d.merged
```

**Pros:**
- True filesystem-level merge — individual files overlay correctly
- A project can override just `restricted.sh` without duplicating `tool.json`

**Cons:**
- Requires `SYS_ADMIN` capability or `--privileged` (defeats isolation goals)
- Linux-only (no macOS Docker Desktop support via VM)
- Added complexity for a small benefit

### Recommendation

**Pattern A (Dual Mount + Entrypoint Merge)** is the best fit for this project.
It's simple, requires no elevated privileges, works on all platforms, and the
copy overhead is negligible for config files. The merge can be file-granular
(copy individual files, not just whole tool dirs) if needed.

---

## 2. Other Docker Features for UX Improvement

### 2a. tmpfs Mounts for Ephemeral/Scratch Data

Use `tmpfs` for data that shouldn't persist between runs.

```yaml
services:
  tool-server:
    tmpfs:
      - /tmp:size=100m
      - /app/tools.d.merged:size=10m
```

**Use cases:**
- Merged tool directories (Pattern A above)
- Temporary build artifacts
- Scratch space that's automatically cleaned up

**UX benefit:** No stale files between runs, faster I/O for temp data.

### 2b. Read-Only Root Filesystem

Lock down the container to prevent unexpected writes.

```yaml
services:
  tool-server:
    read_only: true
    tmpfs:
      - /tmp
      - /run
      - /app/tools.d.merged
```

**UX benefit:** Stronger security guarantee — users know nothing outside the
workspace and designated writable paths can be modified.

### 2c. Docker Secrets / Config Objects

For sensitive values like API keys, Docker secrets are cleaner than environment
variables (which show up in `docker inspect`).

```yaml
# docker-compose.yaml
services:
  claude:
    secrets:
      - anthropic_api_key
    environment:
      - ANTHROPIC_API_KEY_FILE=/run/secrets/anthropic_api_key

secrets:
  anthropic_api_key:
    file: ~/.anthropic/api_key
```

**UX benefit:** Keys don't leak into process listings or container metadata.
More secure default for users who care about credential hygiene.

### 2d. Docker Init Containers (Compose `depends_on` + `service_completed_successfully`)

Run one-time setup before the main containers start.

```yaml
services:
  tool-init:
    image: tool-server:v2
    command: /app/merge-tools.sh
    volumes:
      - ${CLAUDE_HOME}/tools.d:/app/tools.d:ro
      - ${PROJECT_DIR}/.claude-container/tools.d:/app/tools.d.project:ro
      - merged-tools:/app/tools.d.merged

  tool-server:
    depends_on:
      tool-init:
        condition: service_completed_successfully
    volumes:
      - merged-tools:/app/tools.d:ro

volumes:
  merged-tools:
```

**UX benefit:** Clean separation of setup vs. runtime. The tool-server only
starts after merging is complete, avoiding race conditions.

### 2e. Project-Local `.claude-container.yaml` Config

Let repos ship a config file that `run.sh` picks up automatically.

```yaml
# my-project/.claude-container.yaml
tools:
  git:
    restricted: true    # Use the repo's restricted.sh
    timeout: 600
  npm:
    blocked: true       # Disallow npm entirely in this repo

extra_mounts:
  - source: ./scripts
    target: /app/scripts
    readonly: true
```

`run.sh` reads this and generates extra `--volume` and `--env` flags.

**UX benefit:** Repo maintainers declare intent in version control. No manual
per-project Docker configuration by the user.

### 2f. Named Volumes for Tool Caches

Persist tool caches (npm, pip, cargo) across container rebuilds.

```yaml
services:
  tool-server:
    volumes:
      - npm-cache:/home/appuser/.npm
      - pip-cache:/home/appuser/.cache/pip

volumes:
  npm-cache:
  pip-cache:
```

**UX benefit:** Dramatically faster tool setup on subsequent runs. `npm install`
doesn't re-download the world every time.

### 2g. Multi-Stage Build for Tool Binaries

Instead of installing every tool at image build time, use multi-stage builds to
copy only the binaries needed.

```dockerfile
# Stage 1: Build or fetch tool binaries
FROM ubuntu:24.04 AS tool-builder
RUN apt-get update && apt-get install -y git gh curl jq

# Stage 2: Minimal runtime
FROM python:3.12-slim
COPY --from=tool-builder /usr/bin/git /usr/bin/git
COPY --from=tool-builder /usr/bin/gh /usr/bin/gh
COPY --from=tool-builder /usr/bin/curl /usr/bin/curl
COPY --from=tool-builder /usr/bin/jq /usr/bin/jq
```

**UX benefit:** Smaller images, faster pulls, explicit about which tools are
available.

### 2h. Docker Compose Profiles for Tool Sets

Let users opt into tool groups without editing compose files.

```yaml
services:
  tool-server:
    # Always runs — provides core tools (git, etc.)
    build:
      context: .
      dockerfile: tool-server/Containerfile

  tool-server-web:
    profiles: ["web"]
    # Additional container with curl, wget, etc.
    volumes:
      - web-tools:/app/tools.d:ro

  tool-server-build:
    profiles: ["build"]
    # Additional container with npm, cargo, make, etc.
```

```bash
# User chooses what they need
docker compose --profile web --profile build up
```

**UX benefit:** Users don't pay for tools they don't use. Opt-in rather than
all-or-nothing.

---

## 3. Proposed Architecture for Repo-Provided Wrappers

Combining the best options above:

```
LAYER PRECEDENCE (highest wins):
┌─────────────────────────────────────────┐
│  3. Project-local tools.d               │  ← Repo ships .claude-container/
│     ${PROJECT_DIR}/.claude-container/   │     tools.d/git/restricted.sh
├─────────────────────────────────────────┤
│  2. User global tools.d                 │  ← User configures
│     ~/.claude-container/tools.d/        │     ~/.claude-container/tools.d/
├─────────────────────────────────────────┤
│  1. Built-in defaults                   │  ← Baked into container image
│     /app/tools.d/ (from repo)           │     tools.d/ in source repo
└─────────────────────────────────────────┘
```

### Merge Strategy

For each tool, files are resolved individually with higher layers winning:

```
git/tool.json       → Use built-in (layer 1) — repo shouldn't change binary path
git/restricted.sh   → Use project-local (layer 3) — repo defines its own rules
git/setup.sh        → Use user global (layer 2) — user's preferred git config
npm/restricted.py   → Use project-local (layer 3) — repo blocks certain npm cmds
npm/tool.json       → Use built-in (layer 1) — npm binary location is fixed
```

### Implementation Sketch

Changes needed:
1. **`run.sh`**: Detect `${PROJECT_DIR}/.claude-container/tools.d/` and add
   volume mount if present
2. **`tool-setup.sh`**: Add merge step before tool discovery
3. **`tool-caller.py`**: Update `TOOLS_DIR` to point at merged directory (or
   add a second search path in `find_wrapper()` and `discover_tools()`)
4. **`docker-compose.yaml`**: Add optional project-local mount + tmpfs for
   merged output

### Security Considerations

Repos providing restriction wrappers are **additive restrictions** — they can
only make things more restrictive, not less. The merge logic should enforce:

- `tool.json` from project-local is **ignored** (binary paths are trusted from
  global/built-in only)
- `restricted.*` from project-local is applied **in addition to** (not instead
  of) global restrictions — both must pass
- `setup.sh` from project-local runs in a sandbox or is skipped entirely
  (arbitrary code execution risk from untrusted repos)

This means the wrapper chain becomes:

```
Request → Global restricted.sh → Project restricted.sh → Binary
          (must pass)            (must also pass)
```

Rather than project overriding global.

---

## 4. Summary of Recommendations

| Feature | Effort | UX Impact | Security Impact |
|---------|--------|-----------|-----------------|
| Repo-local tools.d (Pattern A) | Medium | High | Needs careful layering |
| tmpfs for merged dirs | Low | Medium | Positive (no persistence) |
| Docker secrets for API keys | Low | Medium | Positive |
| Named volumes for caches | Low | High | Neutral |
| `.claude-container.yaml` config | Medium | High | Needs validation |
| Read-only root filesystem | Low | Low | Positive |
| Compose profiles for tool sets | Medium | Medium | Neutral |
| Multi-stage builds | Low | Medium | Positive (smaller surface) |

**Highest-value next steps:**
1. Repo-local `.claude-container/tools.d/` with dual-mount merge
2. Named volumes for tool caches (npm, pip)
3. Docker secrets for `ANTHROPIC_API_KEY`

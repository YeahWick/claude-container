FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies (no git/gh - those go through agent)
RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    gnupg \
    jq \
    socat \
    python3 \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js (LTS version)
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code globally
RUN npm install -g @anthropic-ai/claude-code

# Create non-root user
RUN useradd -m -s /bin/bash -u 1000 claude
USER claude
WORKDIR /home/claude

# Create directories
RUN mkdir -p /workspace /home/claude/bin

# Copy CLI wrappers (git, gh, curl -> forward to agent)
COPY --chown=claude:claude cli/ /home/claude/bin/
RUN chmod +x /home/claude/bin/*

# CLI wrappers first in PATH to shadow real commands
ENV PATH="/home/claude/bin:${PATH}"

# Copy startup script
COPY --chown=claude:claude start.sh /home/claude/start.sh
RUN chmod +x /home/claude/start.sh

WORKDIR /workspace

ENTRYPOINT ["/home/claude/start.sh"]

# Second Shift Augie — Claude Code + Piper voice helper, one container.
#
# Single-stage build. The image is heavier than I'd like (~700MB) because
# claude-code and node ship a lot, but a multi-stage split would only
# trim ~100MB while making the user's pull/iterate loop slower. Pragmatic
# choice for a home lab: keep it one stage, fast to rebuild.

FROM node:22-bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# System deps:
#   - python3 + venv: voice helper + augie-speak MCP server
#   - ffmpeg: nextcord uses it to encode WAV→Opus for Discord voice
#   - libopus0 + libsodium23: PyNaCl runtime, voice gateway encryption
#   - curl + ca-certificates: HTTP probes, plus bun installer fallback
#   - tini: PID-1 signal handling so docker stop actually terminates
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv python3-full \
        ffmpeg libopus0 libsodium23 \
        curl ca-certificates tini \
    && rm -rf /var/lib/apt/lists/*

# Bun is what the Claude Code Discord plugin's .mcp.json invokes for its
# stdio server (it ships server.ts and expects `bun run start`). Install
# globally via npm so it's on PATH for every user.
RUN npm install -g bun@1.1.34 \
    && npm install -g @anthropic-ai/claude-code@2.1.140 \
    && npm cache clean --force

# Match the host UID/GID so the bind-mounted ~/.claude/ keeps consistent
# ownership. node:22 ships a `node` user at UID 1000 already — rename
# rather than recreate to avoid the "uid in use" error.
RUN usermod -l augie -d /home/augie -m node \
    && groupmod -n augie node

USER augie
ENV HOME=/home/augie
WORKDIR /home/augie/app

# Single venv shared by the voice helper and the augie-speak MCP server.
# Both have tiny dep footprints — one file, one venv.
COPY --chown=augie:augie requirements.txt /tmp/requirements.txt
RUN python3 -m venv /home/augie/.venv \
    && /home/augie/.venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

# Source.
COPY --chown=augie:augie voice/ ./voice/
COPY --chown=augie:augie mcp_bridge/ ./mcp_bridge/
COPY --chown=augie:augie augie-mcp.json ./augie-mcp.json
COPY --chown=augie:augie entrypoint.sh /home/augie/entrypoint.sh

# entrypoint.sh forwards SIGTERM to both children. tini ensures it
# actually receives them.
ENTRYPOINT ["/usr/bin/tini", "--", "/home/augie/entrypoint.sh"]

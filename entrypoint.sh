#!/usr/bin/env bash
# Container entrypoint: voice helper in the background, claude in the
# foreground. Both connect to Discord with the same bot token from the
# mounted ~/.claude/channels/discord/.env. SIGTERM gets forwarded to
# both children so `docker stop` is graceful.

set -euo pipefail

LOG="[augie-entrypoint]"

cd /home/augie/app

# Sanity-check the mount that holds the bot token + access policy.
TOKEN_PATH="$HOME/.claude/channels/discord/.env"
if [[ ! -r "$TOKEN_PATH" ]]; then
  echo "$LOG FATAL: $TOKEN_PATH unreadable — is ~/.claude mounted from the host?" >&2
  exit 1
fi

# Voice helper in the background. Listens on AUGIE_HTTP_BIND for the
# MCP bridge, registers slash commands on Discord. Logs flow to stdout
# so docker logs picks them up.
echo "$LOG starting voice helper..."
/home/augie/.venv/bin/python -m voice &
VOICE_PID=$!

# Trap SIGTERM/SIGINT and forward to both children. tini handles PID 1.
cleanup() {
  echo "$LOG shutting down (voice pid=$VOICE_PID)" >&2
  kill -TERM "$VOICE_PID" 2>/dev/null || true
  wait "$VOICE_PID" 2>/dev/null || true
}
trap cleanup TERM INT

# Foreground: Claude Code with the Discord plugin. The plugin's event
# loop holds this process open indefinitely. Including augie-mcp.json
# via --mcp-config gives Claude the speak_in_voice / voice_status tools.
#
# NOTE: --strict-mcp-config would also drop the host's mcp servers
# (HomeAssistantMCP, etc.). We DON'T want that — those are useful in DMs
# too. So --mcp-config without --strict layers the augie tools on top.
echo "$LOG starting claude --channels ..."
exec claude \
  --channels plugin:discord@claude-plugins-official \
  --mcp-config /home/augie/app/augie-mcp.json

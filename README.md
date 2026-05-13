# Second Shift Augie

Second Shift Augie is a Discord bot with two voices: a text mind powered by [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (via the official Discord plugin) and a HAL-9000 mouth powered by [Piper TTS](https://github.com/rhasspy/piper). The whole bot — chat surface, slash commands, audio pipeline, MCP bridge — lives in **one Docker container**.

This repo started in 2022 as an Ollama + VoxCPM experiment. It was rebuilt mercilessly in May 2026 onto the home-server infrastructure it now relies on: a Mac mini running Plex, Immich, Home Assistant, n8n, and a Piper instance at `10.0.0.72:5050`. The old code is in `main`'s history if you want a museum tour.

---

## What it does

- **DM the bot** → Claude Code answers as `Second_Shift_Augie`. The Discord plugin handles all message ferrying — replies, reactions, threading, file attachments.
- **`/join` in your server** → bot joins your current voice channel.
- **`/play <text>`** → bot speaks `<text>` in HAL's voice (via Piper).
- **DM Claude "say hi in voice"** → Claude calls a `speak_in_voice` MCP tool that routes audio into the channel.
- **`/leave`** → bot disconnects from voice.
- **`/health`** → quick state check.

---

## Architecture

```
┌──────────────────  Docker host (home server)  ──────────────────┐
│                                                                  │
│  Container: second-shift-augie  (host networking)                │
│                                                                  │
│  ┌─ entrypoint.sh ─────────────────────────────────────────┐    │
│  │  bg ► python -m voice           (nextcord gateway #2)    │    │
│  │  fg ► claude --channels         (Discord plugin GW #1)   │    │
│  │      └─ stdio MCP: augie-speak  (calls loopback :9876)   │    │
│  └─────────────────────────────────────────────────────────┘    │
│        │ Piper HTTP                  │ Discord WebSocket          │
│        ▼                             ▼                            │
│   10.0.0.72:5050              Discord Gateway                     │
│   (Piper / HAL)                                                  │
└──────────────────────────────────────────────────────────────────┘
```

Two processes, one bot identity. Both connect to Discord's gateway with the same token (which Discord normally tolerates for single-server bots). They partition events naturally: Claude Code listens to `messageCreate`, the voice helper only handles `interactionCreate` (slash commands) and its own loopback HTTP. If your usage triggers gateway session rotation, the fix is to add a second Discord bot identity for voice — see [Two-bot fallback](#two-bot-fallback) below.

---

## Quickstart

Prereqs on the host:

1. **Docker + Compose** (tested on Docker 29.x).
2. **Claude Code** already installed and authenticated as the user that owns this directory (`~/.claude/.credentials.json` exists).
3. **Discord plugin** installed and configured:
   ```bash
   # In a normal Claude Code session, once:
   /discord:configure        # paste bot token
   /discord:access           # add your Discord user ID
   ```
   This populates `~/.claude/channels/discord/.env` and `access.json`, which the container mounts.
4. **Piper TTS** reachable. See `~/piper-tts/docker-compose.yml` if you also run it on this box.
5. **Scratch directory:**
   ```bash
   sudo mkdir -p /mnt/storage/shares/augie-tmp
   sudo chown $(id -u):$(id -g) /mnt/storage/shares/augie-tmp
   ```

Build and run:

```bash
cd ~/work/SecondShiftAugie
docker compose build
docker compose up -d
```

Or use the `augie` wrapper (see [Operations](#operations)):

```bash
augie on
augie log
```

---

## Configuration

Environment variables, all optional, with the values used in production:

| Var | Default | Notes |
|---|---|---|
| `AUGIE_PIPER_URL` | `http://10.0.0.72:5050` | Piper HTTP endpoint. JSON POST, WAV back. |
| `AUGIE_HTTP_BIND` | `127.0.0.1:9876` | Loopback API for the augie-speak MCP server. Don't expose publicly. (9100 is taken on this host by node-exporter.) |
| `AUGIE_LOG_LEVEL` | `info` | `debug` is chatty but useful. |
| `AUGIE_GUILD_ID` | _(unset)_ | If set, slash commands register instantly to that guild. Without it, expect up to ~1h Discord propagation on first deploy. |
| `AUGIE_IDLE_LEAVE_SECONDS` | `600` | Not yet implemented; reserved. |
| `AUGIE_TMPDIR` | `/tmp/augie` | Scratch dir for WAVs inside the container. Mounted from `/mnt/storage/shares/augie-tmp` on the host. |
| `TZ` | `America/Chicago` | For log timestamps. |

The **Discord bot token** is not configured here. It's read from the mounted `~/.claude/channels/discord/.env`, which the `/discord:configure` skill on the host manages.

---

## Slash commands

All commands are access-gated against the same `access.json` the Claude Code Discord plugin uses (the `allowFrom` list). Grant access with `/discord:access` on the host — works for both DMs and slash commands.

| Command | What it does |
|---|---|
| `/join` | Joins the voice channel you're currently in. Moves between channels if already connected elsewhere. |
| `/leave` | Disconnects and drains the audio queue. |
| `/play <text>` | Synthesizes via Piper and queues for playback. Up to 500 chars. |
| `/health` | Shows Piper reachability, voice connection state, queue depth. |

---

## The MCP tool

`augie-speak` is a tiny stdio MCP server that ships with the container. It exposes two tools to Claude Code:

- `speak_in_voice(text)` — synthesize and play. Returns `ok (queued in #channel, depth=N)`, or `no_voice_connection` if Augie isn't currently in a voice channel.
- `voice_status()` — check Piper reachability and current voice connections.

Claude can call these on its own when context warrants it. Typical interaction:

> **You (in DM):** Augie, I'm in voice now. Say hi.
> **Claude:** _(calls `speak_in_voice("Hi August.")`)_ Said it.

If Augie isn't in voice yet, Claude will either ask you to `/join` first or chain a polite text reply.

The MCP server is registered via `augie-mcp.json` and loaded into Claude with the `--mcp-config` flag in `entrypoint.sh`. Host MCP servers (`HomeAssistantMCP`, etc.) are still available in DMs because we layer rather than override.

---

## Operations

The `augie` host wrapper is in `scripts/augie` — copy it to `~/.local/bin/augie` once.

```
augie on        # docker compose up -d
augie off       # docker compose stop
augie restart   # docker compose restart
augie status    # docker compose ps
augie log       # docker compose logs -f --tail=200
augie attach    # docker exec -it second-shift-augie bash
augie build     # docker compose build
augie rebuild   # build --no-cache + force-recreate
```

### Watchdog → Telegram

`second-shift-augie-alert.sh` (already on the host from the systemd era) posts to the `9bikkMqx5khJmLhW` n8n watchdog workflow on failure, which fans out to Telegram. The new pipeline:

```
docker events → augie-docker-watchdog.service → alert.sh → n8n → Telegram
```

The unit file is in `scripts/augie-docker-watchdog.service` — install with `systemctl --user enable --now`.

### Nightly auto-off

`crontab -e`:

```cron
CRON_TZ=America/Chicago
0 2 * * * /usr/bin/docker stop second-shift-augie
```

You start it back up manually in the morning with `augie on`.

---

## Two-bot fallback (required for voice)

Single-bot turned out not to work for voice — Discord routes `VOICE_SERVER_UPDATE` non-deterministically when one bot identity has two main gateway sessions (claude's discord.js plugin + nextcord both hold one), leaving voice.py without credentials and triggering WebSocket close `4006`. Solution: a second Discord application whose only job is voice.

Setup:

1. **Create a second Discord application** at https://discord.com/developers/applications. Name it whatever — `Second Shift Augie Voice` is what we use. Click *Bot* in the sidebar, enable *Server Members Intent*, then *Reset Token* and copy the token immediately (it's shown only once).
2. **Invite the bot to your server.** *OAuth2* → *URL Generator*, scopes: `bot`, permissions: `Connect`, `Speak`, `Use Voice Activity`, `View Channels`. Open the generated URL, pick the server, authorize.
3. **Hand the token to compose** by writing `~/work/SecondShiftAugie/.env`:
   ```
   AUGIE_VOICE_BOT_TOKEN=<the token>
   ```
   `voice/config.py` checks `AUGIE_VOICE_BOT_TOKEN` first; with it set, voice.py boots as the new bot identity. Claude Code's Discord plugin keeps reading from `~/.claude/channels/discord/.env`, so the text bot is unaffected.
4. **Restart**: `augie restart`. You'll see two members in your server now — the original Augie does text DMs, the second one joins voice channels.

---

## Development

```
SecondShiftAugie/
├── voice/
│   ├── __main__.py        # entry: python -m voice
│   ├── config.py          # env + access.json + token resolution
│   ├── access.py          # access.json gating
│   ├── piper_client.py    # POST to Piper, return WAV path
│   ├── audio_queue.py     # serial per-guild playback
│   ├── slash_commands.py  # /join, /leave, /play, /health
│   └── http_server.py     # aiohttp loopback API (:9100)
├── mcp_bridge/
│   └── augie_speak.py     # stdio MCP server → loopback HTTP
├── Dockerfile             # node:22-slim + python + ffmpeg + claude-code + bun
├── docker-compose.yml
├── entrypoint.sh          # voice (bg) + claude (fg)
├── augie-mcp.json         # --mcp-config payload
├── requirements.txt       # nextcord, aiohttp, dotenv, PyNaCl, mcp
└── scripts/
    ├── augie              # docker-compose wrapper for host
    └── augie-docker-watchdog.service
```

To iterate on Python without rebuilding the image:

```bash
docker compose stop
docker compose run --rm --service-ports augie /home/augie/.venv/bin/python -m voice
```

Or run the voice helper directly on the host (against your local nextcord install):

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
DISCORD_BOT_TOKEN=$(grep DISCORD_BOT_TOKEN ~/.claude/channels/discord/.env | cut -d= -f2) \
  AUGIE_HTTP_BIND=127.0.0.1:9100 \
  AUGIE_PIPER_URL=http://10.0.0.72:5050 \
  .venv/bin/python -m voice
```

---

## History

- **2022** — first release as a nextcord bot driving Ollama Qwen2.5 + VoxCPM TTS voice cloning. Lived mostly on `main` and `reawakening` branches.
- **2026-05-13** — rewritten on branch `claude-rewrite`. Brain replaced with Claude Code; voice replaced with Piper HAL; everything containerized.

The `main` branch still has the old code. The two architectures share a name and not much else.

---

## License

MIT (see `LICENSE`).

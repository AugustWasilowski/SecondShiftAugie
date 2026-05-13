"""Config loading for the voice helper.

The bot token is intentionally NOT in this container's env — it's read
from the same ~/.claude/channels/discord/.env that the Claude Code
Discord plugin uses. That keeps a single source of truth: whatever the
text bot uses, the voice helper uses. Mounting the channels dir into the
container is enough.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

logger = logging.getLogger(__name__)

# The Discord plugin stores its token here. Mounted from the host.
DISCORD_ENV_PATH = Path.home() / ".claude" / "channels" / "discord" / ".env"


def _read_bot_token() -> str:
    """Resolve the Discord bot token for the voice helper.

    Order:
        1. AUGIE_VOICE_BOT_TOKEN — voice-helper-only override. Use this
           when running the two-bot pattern: a separate Discord
           application for voice, distinct from the one Claude Code's
           Discord plugin uses for text. Solves the dual-IDENTIFY voice
           gateway 4006 issue (the discord.js plugin and nextcord both
           open main gateway WSes under one bot identity, and Discord
           routes VOICE_SERVER_UPDATE to whichever it picks first).
        2. DISCORD_BOT_TOKEN in process env (legacy / single-bot setup).
        3. DISCORD_BOT_TOKEN inside ~/.claude/channels/discord/.env
           (managed by the /discord:configure skill on the host).
    """
    voice_token = os.environ.get("AUGIE_VOICE_BOT_TOKEN")
    if voice_token:
        return voice_token

    env_token = os.environ.get("DISCORD_BOT_TOKEN")
    if env_token:
        return env_token

    if DISCORD_ENV_PATH.is_file():
        values = dotenv_values(DISCORD_ENV_PATH)
        token = values.get("DISCORD_BOT_TOKEN")
        if token:
            return token

    raise RuntimeError(
        f"No Discord bot token. Set AUGIE_VOICE_BOT_TOKEN (recommended for "
        f"two-bot setup) or DISCORD_BOT_TOKEN in env, or run the "
        f"/discord:configure skill on the host to write {DISCORD_ENV_PATH}."
    )


def _parse_bind(value: str) -> tuple[str, int]:
    host, _, port = value.partition(":")
    if not port:
        raise ValueError(f"AUGIE_HTTP_BIND must be host:port, got {value!r}")
    return host, int(port)


@dataclass(frozen=True)
class AugieConfig:
    bot_token: str
    piper_url: str
    http_host: str
    http_port: int
    log_level: str
    guild_id: int | None
    idle_leave_seconds: int
    tmpdir: Path

    @classmethod
    def from_env(cls) -> "AugieConfig":
        bind = os.environ.get("AUGIE_HTTP_BIND", "127.0.0.1:9100")
        host, port = _parse_bind(bind)

        guild_id_raw = os.environ.get("AUGIE_GUILD_ID", "").strip()
        guild_id = int(guild_id_raw) if guild_id_raw else None

        tmpdir = Path(os.environ.get("AUGIE_TMPDIR", "/tmp/augie"))
        tmpdir.mkdir(parents=True, exist_ok=True)

        return cls(
            bot_token=_read_bot_token(),
            piper_url=os.environ.get("AUGIE_PIPER_URL", "http://10.0.0.72:5050"),
            http_host=host,
            http_port=port,
            log_level=os.environ.get("AUGIE_LOG_LEVEL", "info"),
            guild_id=guild_id,
            idle_leave_seconds=int(os.environ.get("AUGIE_IDLE_LEAVE_SECONDS", "600")),
            tmpdir=tmpdir,
        )

    def log_level_int(self) -> int:
        return getattr(logging, self.log_level.upper(), logging.INFO)

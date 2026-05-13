"""Loopback HTTP API the augie-speak MCP server calls into.

Routes:
    POST /speak {"text": "...", "guild_id": optional}
        Synthesize via Piper, enqueue playback in the bot's current
        voice connection. If guild_id is omitted, picks the first
        connected voice client (only one home server, so usually safe).

    GET /health
        Bot connection state, Piper reachability, queue depth.
"""

from __future__ import annotations

import logging
from typing import Optional

from aiohttp import web
from nextcord import VoiceClient
from nextcord.ext import commands

from . import piper_client
from .audio_queue import AudioQueue
from .config import AugieConfig

logger = logging.getLogger(__name__)


def _find_voice(
    bot: commands.Bot, guild_id: Optional[int]
) -> Optional[VoiceClient]:
    if guild_id is not None:
        guild = bot.get_guild(guild_id)
        if guild and guild.voice_client and guild.voice_client.is_connected():
            return guild.voice_client
        return None

    for vc in bot.voice_clients:
        if vc.is_connected():
            return vc
    return None


def build_app(
    bot: commands.Bot,
    config: AugieConfig,
    queue: AudioQueue,
) -> web.Application:
    app = web.Application()

    async def speak(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"status": "bad_json"}, status=400)

        text = (body.get("text") or "").strip()
        if not text:
            return web.json_response({"status": "empty_text"}, status=400)

        guild_id = body.get("guild_id")
        if guild_id is not None:
            try:
                guild_id = int(guild_id)
            except (TypeError, ValueError):
                return web.json_response({"status": "bad_guild_id"}, status=400)

        voice = _find_voice(bot, guild_id)
        if voice is None:
            return web.json_response(
                {"status": "no_voice_connection"}, status=409
            )

        try:
            wav = await piper_client.synthesize(
                text=text,
                base_url=config.piper_url,
                tmpdir=config.tmpdir,
            )
        except piper_client.PiperError as exc:
            return web.json_response(
                {"status": "piper_error", "detail": str(exc)}, status=502
            )

        await queue.enqueue(voice, wav)
        return web.json_response(
            {
                "status": "ok",
                "guild_id": voice.guild.id,
                "channel": voice.channel.name if voice.channel else None,
                "queue_depth": queue.depth(voice.guild.id),
            }
        )

    async def health(_request: web.Request) -> web.Response:
        piper_ok = await piper_client.health_check(config.piper_url)
        connected = [
            {
                "guild_id": vc.guild.id,
                "channel": vc.channel.name if vc.channel else None,
                "queue_depth": queue.depth(vc.guild.id),
            }
            for vc in bot.voice_clients
            if vc.is_connected()
        ]
        return web.json_response(
            {
                "ok": piper_ok and bot.is_ready(),
                "bot_ready": bot.is_ready(),
                "piper_ok": piper_ok,
                "voice_connections": connected,
            }
        )

    app.router.add_post("/speak", speak)
    app.router.add_get("/health", health)
    return app


async def run(
    bot: commands.Bot,
    config: AugieConfig,
    queue: AudioQueue,
) -> web.AppRunner:
    """Start the HTTP server on the bot's event loop. Returns the runner so the caller can clean it up."""
    app = build_app(bot, config, queue)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, config.http_host, config.http_port)
    await site.start()
    logger.info(
        "augie HTTP API listening on %s:%d", config.http_host, config.http_port
    )
    return runner

"""Entry point: `python -m voice` boots the helper.

Connects to Discord with the same bot token Claude Code's Discord plugin
uses (read from ~/.claude/channels/discord/.env), registers slash
commands, starts the loopback HTTP API for the MCP bridge, and stays
running until SIGTERM.
"""

from __future__ import annotations

import asyncio
import logging
import signal

import nextcord
from nextcord.ext import commands

from . import slash_commands
from . import http_server
from .audio_queue import AudioQueue
from .config import AugieConfig


def _setup_logging(level: int) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )
    # nextcord is chatty at INFO; bump to WARNING unless we're debugging.
    if level > logging.DEBUG:
        logging.getLogger("nextcord").setLevel(logging.WARNING)
        logging.getLogger("nextcord.client").setLevel(logging.WARNING)
        logging.getLogger("nextcord.gateway").setLevel(logging.WARNING)


async def _amain() -> None:
    config = AugieConfig.from_env()
    _setup_logging(config.log_level_int())
    log = logging.getLogger("voice")

    intents = nextcord.Intents.none()
    # We need guilds for voice channel lookups, voice_states to know when
    # users join/leave (idle leave logic), and members for resolving
    # users in slash command interactions. Message content is NOT needed
    # — Claude Code's plugin handles all message traffic.
    intents.guilds = True
    intents.voice_states = True
    intents.members = True

    bot = commands.Bot(intents=intents)
    queue = AudioQueue()
    slash_commands.register(bot, config, queue)

    @bot.event
    async def on_ready():
        log.info(
            "logged in as %s (id=%s); guilds=%d",
            bot.user,
            bot.user.id if bot.user else "?",
            len(bot.guilds),
        )
        for g in bot.guilds:
            log.info("  guild: %s (id=%s)", g.name, g.id)

    # Start HTTP server alongside the bot.
    http_runner = None

    async def runner():
        nonlocal http_runner
        # Connect first so bot.user is populated when HTTP /health is hit.
        bot_task = asyncio.create_task(bot.start(config.bot_token))

        # Give the gateway a moment to identify before binding the HTTP API.
        # If the gateway falls over (bad token, network), bot.start raises
        # and we exit cleanly.
        await asyncio.sleep(2)
        http_runner = await http_server.run(bot, config, queue)

        await bot_task

    # Trap signals at the loop level so docker stop is graceful.
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop_event.set)

    main_task = asyncio.create_task(runner())

    done, _ = await asyncio.wait(
        [main_task, asyncio.create_task(stop_event.wait())],
        return_when=asyncio.FIRST_COMPLETED,
    )

    log.info("shutting down")
    if not main_task.done():
        await bot.close()
        main_task.cancel()
    if http_runner is not None:
        await http_runner.cleanup()


def main() -> None:
    try:
        asyncio.run(_amain())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

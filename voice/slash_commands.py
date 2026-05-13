"""Slash command surface: /join, /leave, /play, /health.

Access-gated via the same access.json the Claude Code Discord plugin
honors. Adding/removing a user via the /discord:access skill on the host
automatically applies here too — we re-read the file on every command.
"""

from __future__ import annotations

import logging

import nextcord
from nextcord.ext import commands

from . import access, piper_client
from .audio_queue import AudioQueue
from .config import AugieConfig

logger = logging.getLogger(__name__)

# Discord caps slash command string options at 6000 chars but a HAL
# voice line that long would be absurd. 500 keeps things sane and
# matches the v1 repo's heuristic.
PLAY_TEXT_MAX = 500


def _kwargs_for_guild(config: AugieConfig) -> dict:
    """Pin commands to one guild for instant registration if guild_id is set."""
    return {"guild_ids": [config.guild_id]} if config.guild_id else {}


async def _gate(interaction: nextcord.Interaction) -> bool:
    """Return True if the caller is allowed. Sends a rejection otherwise."""
    user_id = interaction.user.id if interaction.user else None
    if user_id is None or not access.is_allowed(user_id):
        logger.warning(
            "denying slash command from user_id=%s (not in access.json)",
            user_id,
        )
        await interaction.response.send_message(
            "Not on the allowlist. Ask the operator to run `/discord:access`.",
            ephemeral=True,
        )
        return False
    return True


def register(
    bot: commands.Bot,
    config: AugieConfig,
    queue: AudioQueue,
) -> None:
    """Attach slash commands to bot."""

    guild_kwargs = _kwargs_for_guild(config)

    @bot.slash_command(name="join", description="Have Augie join your voice channel.", **guild_kwargs)
    async def join(interaction: nextcord.Interaction):
        if not await _gate(interaction):
            return
        await interaction.response.defer(ephemeral=True)

        member = interaction.user
        if not isinstance(member, nextcord.Member) or not member.voice or not member.voice.channel:
            await interaction.followup.send(
                "You need to be in a voice channel first.", ephemeral=True
            )
            return

        channel = member.voice.channel
        existing = interaction.guild.voice_client if interaction.guild else None
        if existing and existing.is_connected():
            if existing.channel.id == channel.id:
                await interaction.followup.send(
                    f"Already in {channel.name}.", ephemeral=True
                )
                return
            await existing.move_to(channel)
        else:
            await channel.connect()

        await interaction.followup.send(
            f"Joined {channel.name}.", ephemeral=True
        )

    @bot.slash_command(name="leave", description="Have Augie leave the voice channel.", **guild_kwargs)
    async def leave(interaction: nextcord.Interaction):
        if not await _gate(interaction):
            return
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        voice = guild.voice_client if guild else None
        if not voice or not voice.is_connected():
            await interaction.followup.send("Not in a voice channel.", ephemeral=True)
            return

        await queue.drain(guild.id)
        await voice.disconnect()
        await interaction.followup.send("Left.", ephemeral=True)

    @bot.slash_command(name="play", description="Say something out loud in HAL's voice.", **guild_kwargs)
    async def play(
        interaction: nextcord.Interaction,
        text: str = nextcord.SlashOption(
            description="What Augie should say.",
            required=True,
            max_length=PLAY_TEXT_MAX,
        ),
    ):
        if not await _gate(interaction):
            return
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        voice = guild.voice_client if guild else None
        if not voice or not voice.is_connected():
            await interaction.followup.send(
                "I'm not in a voice channel. Use `/join` first.", ephemeral=True
            )
            return

        try:
            wav = await piper_client.synthesize(
                text=text,
                base_url=config.piper_url,
                tmpdir=config.tmpdir,
            )
        except piper_client.PiperError as exc:
            await interaction.followup.send(f"Piper failed: {exc}", ephemeral=True)
            return

        await queue.enqueue(voice, wav)
        await interaction.followup.send(
            f"Queued. ({queue.depth(guild.id)} in line)", ephemeral=True
        )

    @bot.slash_command(name="health", description="Show Augie's voice/TTS status.", **guild_kwargs)
    async def health(interaction: nextcord.Interaction):
        if not await _gate(interaction):
            return
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        voice = guild.voice_client if guild else None
        piper_ok = await piper_client.health_check(config.piper_url)

        lines = [
            f"**Piper TTS** ({config.piper_url}): {'🟢 reachable' if piper_ok else '🔴 unreachable'}",
            f"**Voice channel**: {'🟢 ' + voice.channel.name if voice and voice.is_connected() else '🔴 not connected'}",
            f"**Queue depth**: {queue.depth(guild.id) if guild else 0}",
        ]
        await interaction.followup.send("\n".join(lines), ephemeral=True)

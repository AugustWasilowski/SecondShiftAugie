"""Per-guild audio playback queue.

One queue, one consumer task per guild. Plays WAVs serially through the
voice client so two near-simultaneous /speak calls don't trample each
other.

Inspired by the v1 repo's `AudioManager` but written against modern
nextcord's `VoiceClient.play(FFmpegPCMAudio(...))` directly — no need
for the old `DiscordBotManager` indirection.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path

import nextcord
from nextcord import VoiceClient

logger = logging.getLogger(__name__)

# Per-clip max wait. Long enough for ~500 chars of HAL but not so long
# that a deadlocked ffmpeg pegs a queue forever.
PLAY_TIMEOUT_SECONDS = 60


class AudioQueue:
    """Serial playback queue, one per guild."""

    def __init__(self) -> None:
        self._queues: dict[int, asyncio.Queue[Path]] = {}
        self._tasks: dict[int, asyncio.Task] = {}

    def depth(self, guild_id: int) -> int:
        q = self._queues.get(guild_id)
        return q.qsize() if q else 0

    async def enqueue(self, voice: VoiceClient, wav_path: Path) -> None:
        """Add a WAV to the guild's queue, starting the consumer if needed."""
        guild_id = voice.guild.id
        queue = self._queues.setdefault(guild_id, asyncio.Queue())
        await queue.put(wav_path)

        task = self._tasks.get(guild_id)
        if task is None or task.done():
            self._tasks[guild_id] = asyncio.create_task(
                self._consume(guild_id, voice),
                name=f"audio-queue-{guild_id}",
            )

    async def drain(self, guild_id: int) -> None:
        """Stop the consumer for a guild (e.g. on /leave)."""
        task = self._tasks.pop(guild_id, None)
        if task and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        queue = self._queues.pop(guild_id, None)
        if queue is not None:
            while not queue.empty():
                try:
                    wav_path = queue.get_nowait()
                    self._cleanup_file(wav_path)
                except asyncio.QueueEmpty:
                    break

    async def _consume(self, guild_id: int, voice: VoiceClient) -> None:
        queue = self._queues[guild_id]
        while True:
            try:
                wav_path = await queue.get()
            except asyncio.CancelledError:
                logger.debug("queue %s cancelled", guild_id)
                return

            try:
                await self._play_one(voice, wav_path)
            except Exception as exc:
                logger.exception("playback failed: %s", exc)
            finally:
                self._cleanup_file(wav_path)
                queue.task_done()

    async def _play_one(self, voice: VoiceClient, wav_path: Path) -> None:
        if not voice.is_connected():
            logger.warning("voice client disconnected before %s could play", wav_path.name)
            return

        # Wait for any in-flight playback to finish; the queue is serial,
        # but a manual play_audio() could have raced ahead.
        while voice.is_playing():
            await asyncio.sleep(0.05)

        source = nextcord.FFmpegPCMAudio(str(wav_path))
        done = asyncio.Event()

        def _after(err: Exception | None) -> None:
            if err is not None:
                logger.error("ffmpeg playback error: %s", err)
            # set_event() must run on the bot loop, not the ffmpeg thread.
            voice.loop.call_soon_threadsafe(done.set)

        voice.play(source, after=_after)
        try:
            await asyncio.wait_for(done.wait(), timeout=PLAY_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            logger.error("playback timed out, force-stopping %s", wav_path.name)
            with contextlib.suppress(Exception):
                voice.stop()

    @staticmethod
    def _cleanup_file(wav_path: Path) -> None:
        with contextlib.suppress(FileNotFoundError):
            wav_path.unlink()

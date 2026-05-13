"""Tiny async client for the Piper TTS server.

Piper at 10.0.0.72:5050 takes JSON {"text": "..."} and returns WAV bytes
(16-bit mono PCM, 22050 Hz). FFmpeg-in-discord.py handles the resample
to Discord's expected 48kHz stereo Opus.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

import aiohttp

logger = logging.getLogger(__name__)

# Piper takes a beat to render long text. The HAL voice clocks in around
# ~1.5x realtime, so 30s covers ~45s of speech — well past the slash
# command 500-char cap.
PIPER_TIMEOUT = aiohttp.ClientTimeout(total=30)


class PiperError(RuntimeError):
    """Piper synthesis failed."""


async def synthesize(text: str, base_url: str, tmpdir: Path) -> Path:
    """POST text to Piper, write WAV to tmpdir, return path."""
    if not text.strip():
        raise PiperError("empty text")

    payload = {"text": text}
    out_path = tmpdir / f"piper_{uuid.uuid4().hex}.wav"

    async with aiohttp.ClientSession(timeout=PIPER_TIMEOUT) as session:
        async with session.post(base_url, json=payload) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise PiperError(
                    f"piper {resp.status}: {body[:200]}"
                )
            data = await resp.read()

    if not data.startswith(b"RIFF"):
        raise PiperError("piper returned non-WAV payload")

    out_path.write_bytes(data)
    logger.debug("piper synth: %d bytes -> %s", len(data), out_path)
    return out_path


async def health_check(base_url: str) -> bool:
    """Probe Piper's /voices endpoint. True if reachable + responsive."""
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=3)
        ) as session:
            async with session.get(f"{base_url}/voices") as resp:
                return resp.status == 200
    except Exception as exc:
        logger.debug("piper health check failed: %s", exc)
        return False

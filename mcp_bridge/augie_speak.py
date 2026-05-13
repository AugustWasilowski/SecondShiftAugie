"""stdio MCP server exposing speak_in_voice → loopback HTTP → voice helper.

Claude Code launches this as a subprocess (configured via augie-mcp.json
and the `--mcp-config` flag in entrypoint.sh). It talks to the voice
helper over `http://127.0.0.1:9100/speak` so Claude can choose to play
audio in whatever voice channel Augie is currently sitting in.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from mcp.server.fastmcp import FastMCP

VOICE_API = os.environ.get("AUGIE_VOICE_API", "http://127.0.0.1:9100")

server = FastMCP("augie-speak")


@server.tool()
def speak_in_voice(text: str, guild_id: str | None = None) -> str:
    """Speak the given text out loud in Augie's current Discord voice channel.

    Use this when the user invites you into voice with /join and you want
    to reply audibly instead of (or in addition to) text. Keep it short
    — under 500 characters works best with the HAL voice.

    Returns one of:
        ok                     — queued, will play in voice
        no_voice_connection    — Augie isn't in a voice channel; ask user to /join
        piper_error: <detail>  — TTS server hiccup
        bad_request: <detail>  — empty text or malformed input

    Args:
        text: What to say. Plain text, max ~500 chars.
        guild_id: Optional Discord guild ID if there's any ambiguity
            about which voice channel to target. Usually omit.
    """
    text = (text or "").strip()
    if not text:
        return "bad_request: empty text"
    if len(text) > 500:
        return f"bad_request: text too long ({len(text)} chars, max 500)"

    payload: dict = {"text": text}
    if guild_id:
        payload["guild_id"] = guild_id

    req = urllib.request.Request(
        f"{VOICE_API}/speak",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=35) as resp:
            body = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode())
            return body.get("status", f"http_{exc.code}")
        except Exception:
            return f"http_{exc.code}"
    except urllib.error.URLError as exc:
        return f"voice_helper_unreachable: {exc.reason}"
    except Exception as exc:
        return f"unexpected_error: {exc}"

    status = body.get("status", "unknown")
    if status == "ok":
        depth = body.get("queue_depth", "?")
        channel = body.get("channel", "?")
        return f"ok (queued in #{channel}, depth={depth})"
    return status


@server.tool()
def voice_status() -> str:
    """Check whether Augie is currently in a voice channel and Piper is reachable."""
    try:
        with urllib.request.urlopen(f"{VOICE_API}/health", timeout=5) as resp:
            body = json.loads(resp.read().decode())
    except Exception as exc:
        return f"voice_helper_unreachable: {exc}"

    parts = [
        f"piper_ok={body.get('piper_ok')}",
        f"bot_ready={body.get('bot_ready')}",
    ]
    conns = body.get("voice_connections") or []
    if conns:
        parts.append(
            "in_voice="
            + ", ".join(
                f"{c['channel']} (guild {c['guild_id']}, queue {c['queue_depth']})"
                for c in conns
            )
        )
    else:
        parts.append("in_voice=false")
    return " | ".join(parts)


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()

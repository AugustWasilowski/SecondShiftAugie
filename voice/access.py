"""Access control — defers to the same access.json the Discord plugin uses.

The Claude Code Discord plugin manages this file via the /discord:access
skill. We just read it for slash command gating, so granting voice access
follows the same workflow as granting DM access (one source of truth).

Re-read on every check rather than caching: the file is tiny (<1KB) and
the user might run /discord:access while the bot is up. Slight stat cost
is fine.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

ACCESS_JSON_PATH = Path.home() / ".claude" / "channels" / "discord" / "access.json"


def is_allowed(user_id: int) -> bool:
    """Return True if user_id is in the Discord plugin's allowFrom list."""
    try:
        data = json.loads(ACCESS_JSON_PATH.read_text())
    except FileNotFoundError:
        logger.warning("access.json missing at %s — denying all", ACCESS_JSON_PATH)
        return False
    except json.JSONDecodeError as exc:
        logger.error("access.json is malformed: %s — denying all", exc)
        return False

    allow_from = data.get("allowFrom") or []
    return str(user_id) in allow_from

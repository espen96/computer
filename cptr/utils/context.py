"""Context estimation for chat compaction.

Uses a character-based heuristic (len/4) to estimate token counts.
A follow-up will add real usage data from API responses for precision.
"""

from __future__ import annotations

from cptr.env import CHAT_COMPACT_TOKEN_THRESHOLD


def estimate_tokens(text: str) -> int:
    """Rough token estimate: len/4 for Latin text."""
    return max(1, len(text) // 4)


def estimate_messages_tokens(messages: list[dict]) -> int:
    """Total estimated tokens for a message list."""
    total = 0
    for m in messages:
        content = m.get("content", "")
        if isinstance(content, list):
            for block in content:
                if block.get("type") == "text":
                    total += estimate_tokens(block.get("text", ""))
                elif block.get("type") in ("image", "image_url"):
                    total += 1000  # rough estimate for images
        else:
            total += estimate_tokens(content)
        # Tool call arguments
        for tc in m.get("tool_calls", []):
            total += estimate_tokens(tc.get("function", {}).get("arguments", ""))
        total += 4  # per-message overhead (role, separators)
    return total


def should_compact(messages: list[dict], system_prompt: str) -> bool:
    """True when estimated tokens exceed the compact token threshold."""
    total = estimate_tokens(system_prompt) + estimate_messages_tokens(messages)
    return total > _get_threshold()


def _get_threshold() -> int:
    """Read threshold: config.toml > env var/default."""
    try:
        from cptr.utils.config import load_config

        config = load_config()
        val = config.get("chat", {}).get("compact_token_threshold")
        if val is not None:
            return int(val)
    except Exception:
        pass
    return CHAT_COMPACT_TOKEN_THRESHOLD

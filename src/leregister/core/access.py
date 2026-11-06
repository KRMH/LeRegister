"""Owner-only access rule (AD-6)."""

from __future__ import annotations


def is_owner(user_id: int | None, chat_type: str | None, owner_id: int) -> bool:
    """True only for the Owner's account in a private chat."""
    return user_id is not None and user_id == owner_id and chat_type == "private"

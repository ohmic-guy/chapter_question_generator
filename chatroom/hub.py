"""
chatroom/hub.py
───────────────
Tiny adapter around AgentScope messages for the chapter team.

The MVP spec says the chapter-wise generator runs inside one MsgHub session per
chapter. This module keeps that boundary isolated so the orchestration code can
be tested without importing AgentScope directly.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Dict, Optional

try:
    from agentscope.message import Msg
except ModuleNotFoundError:  # pragma: no cover - exercised only without agentscope
    from agents.protocols import Msg


def make_msg(name: str, content: Dict[str, Any], role: str = "assistant") -> Msg:
    """Create the message shape expected by AgentScope 2.0 agents."""
    return Msg(name=name, content=content, role=role)


@dataclass
class ChapterAnnouncement:
    """Shared context announced at the start of a chapter team run."""

    chapter_request: Dict[str, Any]
    dedup_index_size: int

    def as_content(self) -> Dict[str, Any]:
        return {
            "chapter_request": self.chapter_request,
            "dedup_index_size": self.dedup_index_size,
        }


class ChapterMsgHub(AbstractContextManager["ChapterMsgHub"]):
    """
    Context boundary for one chapter run.

    The current implementation is intentionally lightweight: concrete agents get
    all required state in each Msg.content. If the project later wires a real
    AgentScope MsgHub, this adapter is the only file that needs to change.
    """

    def __init__(self, announcement: ChapterAnnouncement) -> None:
        self.announcement = announcement
        self.opened = False
        self.announcement_msg: Optional[Msg] = None

    def __enter__(self) -> "ChapterMsgHub":
        self.opened = True
        self.announcement_msg = make_msg(
            name="chapter_team",
            role="system",
            content=self.announcement.as_content(),
        )
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.opened = False


__all__ = ["ChapterAnnouncement", "ChapterMsgHub", "make_msg"]

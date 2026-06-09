"""
api/container.py
────────────────
Small API-side dependency helpers for M8.

Concrete agents are intentionally not constructed here yet; those belong to the
agent implementation tasks. This file owns the shared per-assessment dedup
registry that the API layer can inject into ChapterTeamRunner calls.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Dict

from chatroom.team_runner import ChapterTeamRunner
from models.dedup_index import IDedupIndex, InMemoryDedupIndex


class AssessmentDedupRegistry:
    """
    Stores one dedup index per assessment_id.

    The Planner runs chapters sequentially in the MVP, but API requests may still
    touch the registry concurrently, so access is guarded by a lock.
    """

    def __init__(self) -> None:
        self._indices: Dict[str, IDedupIndex] = {}
        self._lock = threading.Lock()

    def get(self, assessment_id: str) -> IDedupIndex:
        with self._lock:
            if assessment_id not in self._indices:
                self._indices[assessment_id] = InMemoryDedupIndex()
            return self._indices[assessment_id]

    def discard(self, assessment_id: str) -> None:
        with self._lock:
            self._indices.pop(assessment_id, None)

    def reset(self) -> None:
        with self._lock:
            self._indices.clear()


@dataclass
class ChapterGeneratorContainer:
    """Dependencies needed by the chapter-generation API entry point."""

    runner: ChapterTeamRunner
    dedup_registry: AssessmentDedupRegistry = field(
        default_factory=AssessmentDedupRegistry
    )


__all__ = ["AssessmentDedupRegistry", "ChapterGeneratorContainer"]

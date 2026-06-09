"""
models/dedup_index.py
─────────────────────
Cross-chapter dedup index: protocol + default in-memory implementation.

SOLID notes
───────────
  SRP  — one responsibility: track seen question stems; nothing else.
  OCP  — IDedupIndex is the extension point.
         Swap InMemoryDedupIndex for RedisDedupIndex (multi-process) or
         SQLiteDedupIndex (persistent across runs) without touching team_runner.
  LSP  — any IDedupIndex implementation is a drop-in replacement.
  ISP  — interface is minimal: contains(), add(), __len__().
         Callers never need more than these three.
  DIP  — team_runner.py depends on IDedupIndex (abstraction), not the class.

Consumed by
───────────
  chatroom/team_runner.py  — type hint on run()
  api/container.py         — instantiates InMemoryDedupIndex; injects via DI
  api/generator_entry.py   — stores one index per assessment_id

DO NOT import anything from this project here.
Pure stdlib only.
"""

from __future__ import annotations

import re
import threading
from typing import Protocol, runtime_checkable


# ─────────────────────────────────────────────────────────────────────────────
# Protocol (abstraction)
# ─────────────────────────────────────────────────────────────────────────────

@runtime_checkable
class IDedupIndex(Protocol):
    """
    Minimal interface for a cross-chapter question dedup store.

    Implementations must be safe to call from team_runner's refinement loop
    (single-threaded per chapter) but MAY be called concurrently if the
    Planner schedules chapters in parallel in a future version.
    """

    def contains(self, stem: str) -> bool:
        """Return True if a normalised form of stem is already indexed."""
        ...

    def add(self, stem: str) -> None:
        """Index stem so future contains() calls return True for it."""
        ...

    def __len__(self) -> int:
        """Return the number of unique stems currently indexed."""
        ...


# ─────────────────────────────────────────────────────────────────────────────
# Normalisation (shared by all implementations)
# ─────────────────────────────────────────────────────────────────────────────

_WHITESPACE = re.compile(r"\s+")


def _normalise(stem: str) -> str:
    """
    Canonical form used for dedup comparison.

    Steps
    ─────
    1. Strip leading / trailing whitespace.
    2. Collapse internal whitespace runs to a single space.
    3. Lowercase.

    Kept simple for MVP. A future version could add:
      - punctuation stripping
      - stemming / lemmatisation
      - SimHash / MinHash for near-duplicate detection
    """
    return _WHITESPACE.sub(" ", stem.strip()).lower()


# ─────────────────────────────────────────────────────────────────────────────
# InMemoryDedupIndex (default implementation)
# ─────────────────────────────────────────────────────────────────────────────

class InMemoryDedupIndex:
    """
    Thread-safe, in-process dedup index backed by a Python set.

    Lifetime
    ────────
    One instance per assessment run.
    Created in api/container.py and shared across all chapter calls
    belonging to the same assessment_id.
    Discarded when the assessment session ends.

    Thread safety
    ─────────────
    MVP runs chapters sequentially, so locking has zero contention cost.
    The lock is included so parallel chapter execution (future) does not
    require changes here.
    """

    def __init__(self) -> None:
        self._stems: set[str] = set()
        self._lock  = threading.Lock()

    def contains(self, stem: str) -> bool:
        """O(1) lookup after normalisation."""
        with self._lock:
            return _normalise(stem) in self._stems

    def add(self, stem: str) -> None:
        """Add normalised stem. Silently ignores duplicates (set semantics)."""
        with self._lock:
            self._stems.add(_normalise(stem))

    def __len__(self) -> int:
        with self._lock:
            return len(self._stems)

    def __repr__(self) -> str:
        return f"InMemoryDedupIndex(size={len(self)})"


# ─────────────────────────────────────────────────────────────────────────────
# Export list
# ─────────────────────────────────────────────────────────────────────────────

__all__ = [
    "IDedupIndex",
    "InMemoryDedupIndex",
    "_normalise",   # exported so alternative implementations reuse the same logic
]
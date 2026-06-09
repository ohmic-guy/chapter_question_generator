"""
models/chapter_result.py
─────────────────────────
Output contract from ChapterTeamRunner → api/generator_entry.py.

SOLID notes
───────────
  SRP  — carries only the result of one chapter generation run; no logic.
  OCP  — add fields freely; consumers use named access so nothing breaks.
  LSP  — not subclassed; dataclass is intentional (value object, not entity).
  DIP  — team_runner depends on this model, not on a dict; API layer reads it
         via ChapterResponse.from_result() without knowing runner internals.

Design choice: dataclass over Pydantic
───────────────────────────────────────
ChapterResult is an internal value object — it is never deserialised from JSON.
The API layer (ChapterResponse in generator_entry.py) wraps it in a Pydantic
model for serialisation. Using a plain dataclass here keeps the boundary clean:
Pydantic lives at the edges (request / response); dataclasses live inside.

bundles type
────────────
Typed as List[dict] here because qa_bundle.py (file 5) is not yet written.
Once QABundle exists, team_runner.py can tighten the annotation to List[QABundle].
ChapterResult itself does not need to change.

Consumed by
───────────
  chatroom/team_runner.py  — constructs and returns ChapterResult
  api/generator_entry.py   — reads via ChapterResponse.from_result()

DO NOT import anything from this project here.
Pure stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    # Import only for static analysis / IDE support.
    # At runtime this block is skipped — no circular import risk.
    from models.qa_bundle import QABundle


# ─────────────────────────────────────────────────────────────────────────────
# ChapterResult
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ChapterResult:
    """
    Immutable snapshot of what the chapter generator team produced.

    Fields
    ──────
    chapter_id    — mirrors ChapterRequest.chapter_id; ties result to its request.
    bundles       — validated Q&A bundles; each has validation.layer1 == "pass".
    dropped_count — items that failed all max_refine attempts; Planner tops these up.
    sufficient    — False when DataRetrieveAgent flagged too few source chunks.
                    A True here does NOT guarantee dropped_count == 0.
    warnings      — human-readable strings for the Planner log / response body.
    """

    chapter_id:    str
    bundles:       List[dict]         # List[QABundle] once qa_bundle.py is written
    dropped_count: int  = 0
    sufficient:    bool = True
    warnings:      List[str] = field(default_factory=list)

    # ── computed properties ───────────────────────────────────────────────────

    @property
    def passed_count(self) -> int:
        """Number of bundles that passed Layer-1 validation."""
        return len(self.bundles)

    @property
    def total_attempted(self) -> int:
        """passed + dropped — total items the generator tried to produce."""
        return self.passed_count + self.dropped_count

    @property
    def is_degraded(self) -> bool:
        """
        True when the result is incomplete in any way:
          - generator dropped items after max_refine exhaustion, OR
          - DataRetrieve flagged insufficient source chunks.
        The Planner uses this as a fast check before deciding to top up.
        """
        return self.dropped_count > 0 or not self.sufficient

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0

    # ── dunder ────────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"ChapterResult("
            f"chapter_id={self.chapter_id!r}, "
            f"passed={self.passed_count}, "
            f"dropped={self.dropped_count}, "
            f"sufficient={self.sufficient}, "
            f"warnings={len(self.warnings)})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Export list
# ─────────────────────────────────────────────────────────────────────────────

__all__ = ["ChapterResult"]
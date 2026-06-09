"""
models/chapter_request.py
──────────────────────────
Pydantic contract for the Planner → ChapterTeam request.

SOLID notes
───────────
  SRP  — owns only the incoming request schema and its invariants.
  OCP  — add a new QuestionType to the Literal; validators adapt automatically.
  DIP  — M9/M10 import ChapterRequest; they do NOT redefine or shadow it.

Consumed by
───────────
  chatroom/team_runner.py   — run(chapter_request: ChapterRequest, ...)
  api/generator_entry.py    — FastAPI request body
  agents/* (M9, M10)        — read via x.content["chapter_request"]

DO NOT import anything from this project here.
Pure stdlib + pydantic only.
"""

from __future__ import annotations

from typing import Dict, List, Literal

from pydantic import BaseModel, field_validator, model_validator

# ─────────────────────────────────────────────────────────────────────────────
# Type aliases
# ─────────────────────────────────────────────────────────────────────────────

QuestionType = Literal["mcq", "msq", "numerical", "short", "long"]


# ─────────────────────────────────────────────────────────────────────────────
# Sub-models
# ─────────────────────────────────────────────────────────────────────────────

class TypeSpec(BaseModel):
    """One question-type slot in a chapter request."""

    type:  QuestionType
    count: int   # how many questions of this type
    marks: int   # marks awarded per question

    @field_validator("count")
    @classmethod
    def count_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError(f"count must be >= 1, got {v}")
        return v

    @field_validator("marks")
    @classmethod
    def marks_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError(f"marks must be >= 1, got {v}")
        return v


class DifficultySpec(BaseModel):
    """Easy / medium / hard split for one question type."""

    easy:   int
    medium: int
    hard:   int

    @field_validator("easy", "medium", "hard")
    @classmethod
    def non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"difficulty bucket count cannot be negative, got {v}")
        return v

    @property
    def total(self) -> int:
        return self.easy + self.medium + self.hard


# ─────────────────────────────────────────────────────────────────────────────
# Root model
# ─────────────────────────────────────────────────────────────────────────────

class ChapterRequest(BaseModel):
    """
    Sent by the Planner to the chapter generator team.

    Invariants (enforced at parse time)
    ────────────────────────────────────
    1. No duplicate question types in `types`.
    2. Every type in `types` has a matching entry in `difficulty`.
    3. Every type in `difficulty` has a matching entry in `types`.
    4. For each type, difficulty.easy + medium + hard == types.count.

    Example
    ───────
    {
        "assessment_id": "asmt_001",
        "book_id":       "book_phy_11",
        "chapter_id":    "ch_05",
        "subject":       "physics",
        "types": [
            {"type": "mcq",       "count": 10, "marks": 1},
            {"type": "numerical", "count": 5,  "marks": 4}
        ],
        "difficulty": {
            "mcq":       {"easy": 3, "medium": 5, "hard": 2},
            "numerical": {"easy": 1, "medium": 3, "hard": 1}
        }
    }
    """

    assessment_id: str
    book_id:       str
    chapter_id:    str
    subject:       str
    types:         List[TypeSpec]
    difficulty:    Dict[QuestionType, DifficultySpec]

    # ── validators ────────────────────────────────────────────────────────────

    @field_validator("types")
    @classmethod
    def no_duplicate_types(cls, v: List[TypeSpec]) -> List[TypeSpec]:
        seen: set[str] = set()
        for ts in v:
            if ts.type in seen:
                raise ValueError(
                    f"Duplicate question type '{ts.type}' in types list. "
                    "Each type may appear only once."
                )
            seen.add(ts.type)
        return v

    @model_validator(mode="after")
    def difficulty_coverage_and_sums(self) -> ChapterRequest:
        """
        Enforces invariants 2, 3, 4.
        Runs after all field validators, so TypeSpec objects are already valid.
        """
        type_keys  = {ts.type for ts in self.types}
        diff_keys  = set(self.difficulty.keys())
        count_map  = {ts.type: ts.count for ts in self.types}

        # Invariant 2: every requested type has a difficulty breakdown
        missing_diff = type_keys - diff_keys
        if missing_diff:
            raise ValueError(
                f"No difficulty spec for type(s): {sorted(missing_diff)}. "
                "Every entry in 'types' must have a matching 'difficulty' key."
            )

        # Invariant 3: no orphan difficulty keys
        orphan_diff = diff_keys - type_keys
        if orphan_diff:
            raise ValueError(
                f"difficulty key(s) {sorted(orphan_diff)} have no matching "
                "entry in 'types'."
            )

        # Invariant 4: difficulty totals match requested counts
        for q_type, diff_spec in self.difficulty.items():
            if diff_spec.total != count_map[q_type]:
                raise ValueError(
                    f"Difficulty sum for '{q_type}' is {diff_spec.total} "
                    f"(easy={diff_spec.easy} + medium={diff_spec.medium} + "
                    f"hard={diff_spec.hard}), expected {count_map[q_type]}."
                )

        return self

    # ── computed properties ───────────────────────────────────────────────────

    @property
    def total_questions(self) -> int:
        """Total questions requested across all types."""
        return sum(ts.count for ts in self.types)

    @property
    def total_marks(self) -> int:
        """Total marks for this chapter (count × marks per type, summed)."""
        return sum(ts.count * ts.marks for ts in self.types)


# ─────────────────────────────────────────────────────────────────────────────
# Export list
# ─────────────────────────────────────────────────────────────────────────────

__all__ = [
    "QuestionType",
    "TypeSpec",
    "DifficultySpec",
    "ChapterRequest",
]
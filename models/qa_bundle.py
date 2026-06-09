"""
models/qa_bundle.py
────────────────────
Pydantic schema for a single validated Q&A bundle.

This is M10's primary data contract. Every agent in the pipeline produces,
reads, or validates against this shape. team_runner stamps validation.layer1
after the bundle exits the refinement loop.

SOLID notes
───────────
  SRP  — owns only the bundle schema and its structural invariants.
         Content correctness (answer right/wrong) is NOT checked here —
         that is QAValidatorAgent's job.
  OCP  — add a QuestionType → update the Literal; validators auto-adapt
         via the TYPE_RULES dispatch table.
  DIP  — all agents depend on QABundle, not on dict. team_runner imports
         QABundle to tighten its List[dict] annotation once this file exists.

Invariants enforced at parse time
───────────────────────────────────
  1.  stem is non-empty.
  2.  marks >= 1.
  3.  source_chunk_ids is non-empty  (anti-hallucination gate — spec REQUIRED).
  4.  options MUST be present for mcq / msq.
  5.  options MUST be absent  for numerical / short / long.
  6.  option keys are unique within a bundle.
  7.  mcq  → answer.value is a single str matching one option key.
  8.  msq  → answer.value is a list of >= 2 str, each matching an option key.
  9.  numerical / short / long → answer.value is a non-empty str.

Content correctness (answer accuracy, chunk grounding, hardness) is
validated at runtime by QAValidatorAgent — NOT here.

Consumed by
───────────
  agents/qa_validator_agent.py     (M10) — validates bundle content
  agents/subject_generator_agent.py (M9) — produces raw bundles
  agents/component_provider_agent.py(M10) — enriches bundles
  chatroom/team_runner.py           (M8)  — stamps validation.layer1
  api/generator_entry.py            (M8)  — serialised in ChapterResponse

DO NOT import anything from this project except models/chapter_request.py.
"""

from __future__ import annotations

from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator

from models.chapter_request import QuestionType

# ─────────────────────────────────────────────────────────────────────────────
# Type aliases
# ─────────────────────────────────────────────────────────────────────────────

Difficulty      = Literal["easy", "medium", "hard"]
Layer1Status    = Literal["pass", "fail", "pending"]

# ─────────────────────────────────────────────────────────────────────────────
# Sub-models
# ─────────────────────────────────────────────────────────────────────────────

class Option(BaseModel):
    """One option in an MCQ / MSQ question."""

    key:  str   # e.g. "A", "B", "C", "D"
    text: str

    @field_validator("key")
    @classmethod
    def key_single_uppercase(cls, v: str) -> str:
        v = v.strip()
        if len(v) != 1 or not v.isupper():
            raise ValueError(
                f"Option key must be a single uppercase letter (A-Z), got {v!r}"
            )
        return v

    @field_validator("text")
    @classmethod
    def text_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Option text cannot be empty")
        return v


class Answer(BaseModel):
    """
    Correct answer for a bundle.

    value       — str  for mcq / numerical / short / long
                  List[str] for msq (each element is an option key)
    explanation — step-by-step solution; required on every bundle.
    """

    value:       Union[str, List[str]]
    explanation: str

    @field_validator("explanation")
    @classmethod
    def explanation_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Answer explanation cannot be empty")
        return v


class ValidationStatus(BaseModel):
    """
    Stamped by team_runner after the refinement loop.

    pending — bundle has not yet passed Layer-1 (default on creation).
    pass    — QAValidatorAgent cleared all checks; team_runner stamped this.
    fail    — kept for intermediate debug records; never leaves the team.
    """

    layer1: Layer1Status = "pending"


# ─────────────────────────────────────────────────────────────────────────────
# QABundle
# ─────────────────────────────────────────────────────────────────────────────

class QABundle(BaseModel):
    """
    A single validated question-answer bundle.

    Full example (MCQ)
    ──────────────────
    {
        "stem":     "A body of mass 2 kg is moving with velocity 3 m/s. Its KE is?",
        "type":     "mcq",
        "marks":    1,
        "options":  [
            {"key": "A", "text": "6 J"},
            {"key": "B", "text": "9 J"},
            {"key": "C", "text": "12 J"},
            {"key": "D", "text": "18 J"}
        ],
        "answer":   {"value": "B", "explanation": "KE = ½mv² = ½×2×9 = 9 J"},
        "difficulty": "medium",
        "subject":  "physics",
        "source_chunk_ids": ["chunk_phy_11_ch05_003"],
        "validation": {"layer1": "pending"}
    }
    """

    stem:             str
    type:             QuestionType
    marks:            int
    options:          Optional[List[Option]] = None
    answer:           Answer
    difficulty:       Difficulty
    subject:          str
    source_chunk_ids: List[str]
    validation:       ValidationStatus = Field(default_factory=ValidationStatus)

    # ── field-level validators ────────────────────────────────────────────────

    @field_validator("stem")
    @classmethod
    def stem_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("stem cannot be empty")
        return v

    @field_validator("marks")
    @classmethod
    def marks_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError(f"marks must be >= 1, got {v}")
        return v

    @field_validator("source_chunk_ids")
    @classmethod
    def chunks_non_empty(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError(
                "source_chunk_ids cannot be empty. "
                "Every bundle must cite the chunk(s) it was built from. "
                "No citation → item is invalid (spec anti-hallucination control)."
            )
        return v

    @field_validator("options")
    @classmethod
    def option_keys_unique(cls, v: Optional[List[Option]]) -> Optional[List[Option]]:
        if v is None:
            return v
        keys = [opt.key for opt in v]
        if len(keys) != len(set(keys)):
            dupes = [k for k in keys if keys.count(k) > 1]
            raise ValueError(f"Duplicate option keys: {sorted(set(dupes))}")
        return v

    # ── cross-field validators ────────────────────────────────────────────────

    @model_validator(mode="after")
    def enforce_type_rules(self) -> QABundle:
        """
        Dispatch table approach: each question type has explicit rules.
        Adding a new type → add one entry to TYPE_RULES, nothing else changes.
        """
        rules = {
            "mcq":       self._validate_mcq,
            "msq":       self._validate_msq,
            "numerical": self._validate_freeform,
            "short":     self._validate_freeform,
            "long":      self._validate_freeform,
        }
        rules[self.type]()
        return self

    # ── type-specific validators (called by dispatch table) ───────────────────

    def _validate_mcq(self) -> None:
        self._require_options("mcq")
        option_keys = {opt.key for opt in self.options}  # type: ignore[union-attr]

        if not isinstance(self.answer.value, str):
            raise ValueError(
                f"mcq answer.value must be a single str (option key), "
                f"got {type(self.answer.value).__name__}"
            )
        if self.answer.value not in option_keys:
            raise ValueError(
                f"mcq answer.value '{self.answer.value}' is not a valid option key. "
                f"Valid keys: {sorted(option_keys)}"
            )

    def _validate_msq(self) -> None:
        self._require_options("msq")
        option_keys = {opt.key for opt in self.options}  # type: ignore[union-attr]

        if not isinstance(self.answer.value, list):
            raise ValueError(
                "msq answer.value must be a List[str] of correct option keys, "
                f"got {type(self.answer.value).__name__}"
            )
        if len(self.answer.value) < 2:
            raise ValueError(
                f"msq requires >= 2 correct answers, got {len(self.answer.value)}"
            )
        invalid = [k for k in self.answer.value if k not in option_keys]
        if invalid:
            raise ValueError(
                f"msq answer keys {invalid} are not valid option keys. "
                f"Valid keys: {sorted(option_keys)}"
            )

    def _validate_freeform(self) -> None:
        if self.options is not None:
            raise ValueError(
                f"'{self.type}' questions must not have options. "
                "Set options to null/None."
            )
        if not isinstance(self.answer.value, str) or not self.answer.value.strip():
            raise ValueError(
                f"'{self.type}' answer.value must be a non-empty str"
            )

    # ── helpers ───────────────────────────────────────────────────────────────

    def _require_options(self, q_type: str) -> None:
        if not self.options:
            raise ValueError(
                f"'{q_type}' questions require a non-empty options list"
            )

    # ── computed properties ───────────────────────────────────────────────────

    @property
    def is_validated(self) -> bool:
        """True only after team_runner stamps layer1='pass'."""
        return self.validation.layer1 == "pass"

    @property
    def option_count(self) -> int:
        return len(self.options) if self.options else 0


# ─────────────────────────────────────────────────────────────────────────────
# Export list
# ─────────────────────────────────────────────────────────────────────────────

__all__ = [
    "Difficulty",
    "Layer1Status",
    "Option",
    "Answer",
    "ValidationStatus",
    "QABundle",
]

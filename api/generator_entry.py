"""
api/generator_entry.py
──────────────────────
API bridge for the chapter-wise generator.

This module converts the internal ChapterResult dataclass into a serialisable
response model and provides a small callable entry point for the Webrole/FastAPI
layer. It deliberately does not know concrete agent classes.
"""

from __future__ import annotations

from typing import Callable, List, Optional

from pydantic import BaseModel, Field

from api.container import AssessmentDedupRegistry, ChapterGeneratorContainer
from chatroom.team_runner import ChapterTeamRunner
from models.chapter_request import ChapterRequest
from models.chapter_result import ChapterResult

try:
    from fastapi import APIRouter, Depends
except ModuleNotFoundError:  # pragma: no cover - FastAPI is optional here
    APIRouter = None  # type: ignore[assignment]
    Depends = None  # type: ignore[assignment]


class ChapterResponse(BaseModel):
    """Serialisable response returned by the chapter generator endpoint."""

    chapter_id: str
    bundles: List[dict]
    passed_count: int
    dropped_count: int = 0
    total_attempted: int
    sufficient: bool = True
    degraded: bool = False
    warnings: List[str] = Field(default_factory=list)

    @classmethod
    def from_result(cls, result: ChapterResult) -> "ChapterResponse":
        return cls(
            chapter_id=result.chapter_id,
            bundles=result.bundles,
            passed_count=result.passed_count,
            dropped_count=result.dropped_count,
            total_attempted=result.total_attempted,
            sufficient=result.sufficient,
            degraded=result.is_degraded,
            warnings=result.warnings,
        )


def generate_chapter(
    chapter_request: ChapterRequest,
    *,
    runner: ChapterTeamRunner,
    dedup_registry: AssessmentDedupRegistry,
) -> ChapterResponse:
    """
    Run one chapter request and return its serialisable response.

    The dedup index is keyed by assessment_id so cross-chapter repetition is
    caught across all requests belonging to the same assessment.
    """
    result = runner.run(
        chapter_request=chapter_request,
        dedup_index=dedup_registry.get(chapter_request.assessment_id),
    )
    return ChapterResponse.from_result(result)


def build_router(
    get_container: Callable[[], ChapterGeneratorContainer],
    *,
    prefix: str = "/generator",
) -> object:
    """
    Build a FastAPI router when FastAPI is available.

    Concrete applications pass a dependency factory that returns a fully wired
    ChapterGeneratorContainer.
    """
    if APIRouter is None or Depends is None:
        raise RuntimeError("FastAPI is not installed; cannot build generator router.")

    router = APIRouter(prefix=prefix, tags=["chapter-generator"])

    @router.post("/chapter", response_model=ChapterResponse)
    def generate_chapter_endpoint(
        chapter_request: ChapterRequest,
        container: ChapterGeneratorContainer = Depends(get_container),
    ) -> ChapterResponse:
        return generate_chapter(
            chapter_request,
            runner=container.runner,
            dedup_registry=container.dedup_registry,
        )

    return router


__all__ = ["ChapterResponse", "build_router", "generate_chapter"]

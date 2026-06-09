"""
chatroom/team_runner.py
───────────────────────
M8 orchestration for the Chapter-Wise Question Generator.

The runner exposes the mini agent-team as one component to the Planner:

    retrieve chunks -> generate bundles -> provide components -> Layer-1 validate

It owns no subject intelligence. Concrete agents are injected behind protocols,
and this file only coordinates message flow, bounded repair, final stamping,
dedup updates, and ChapterResult construction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple

from agents.protocols import (
    IComponentProviderAgent,
    IDataRetrieveAgent,
    IQAValidatorAgent,
    IRepairable,
    ISubjectGeneratorAgent,
)
from chatroom.defect_router import DefectRouter
from chatroom.hub import ChapterAnnouncement, ChapterMsgHub, make_msg
from models.chapter_request import ChapterRequest
from models.chapter_result import ChapterResult
from models.dedup_index import IDedupIndex
from models.qa_bundle import QABundle


DEFAULT_MAX_REFINE = 2


@dataclass(frozen=True)
class ValidationVerdict:
    """Normalized result from QAValidatorAgent or runner guard checks."""

    passed: bool
    defect_type: Optional[str] = None
    defect_detail: Optional[str] = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ValidationVerdict":
        return cls(
            passed=bool(value.get("passed", False)),
            defect_type=value.get("defect_type"),
            defect_detail=value.get("defect_detail"),
        )

    def as_content(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "defect_type": self.defect_type,
            "defect_detail": self.defect_detail,
        }


class ChapterTeamRunner:
    """
    Runs one chapter request through the Section-6 agent team.

    The Planner creates or receives one instance with concrete agents injected,
    then calls run() for each ChapterRequest. Chapters are intentionally run
    sequentially by the Planner; this class only handles one chapter at a time.
    """

    def __init__(
        self,
        data_retrieve_agent: IDataRetrieveAgent,
        subject_generator_agent: ISubjectGeneratorAgent,
        component_provider_agent: IComponentProviderAgent,
        qa_validator_agent: IQAValidatorAgent,
        *,
        max_refine: int = DEFAULT_MAX_REFINE,
        defect_router: Optional[DefectRouter] = None,
    ) -> None:
        self.data_retrieve_agent = data_retrieve_agent
        self.subject_generator_agent = subject_generator_agent
        self.component_provider_agent = component_provider_agent
        self.qa_validator_agent = qa_validator_agent
        self.max_refine = max_refine
        self.defect_router = defect_router or DefectRouter(
            {
                "citation_missing": (self.subject_generator_agent.name, self.subject_generator_agent.fix),
                "citation_invalid": (self.subject_generator_agent.name, self.subject_generator_agent.fix),
                "consistency": (self.subject_generator_agent.name, self.subject_generator_agent.fix),
                "hardness_mismatch": (self.subject_generator_agent.name, self.subject_generator_agent.fix),
                "ambiguity": (self.subject_generator_agent.name, self.subject_generator_agent.fix),
                "dedup_fail": (self.subject_generator_agent.name, self.subject_generator_agent.fix),
                "answer_wrong": (self.subject_generator_agent.name, self.subject_generator_agent.fix),
                "math_error": (self.component_provider_agent.name, self.component_provider_agent.fix),
                "formula_invalid": (self.component_provider_agent.name, self.component_provider_agent.fix),
                "component_missing": (self.component_provider_agent.name, self.component_provider_agent.fix),
                "sympy_fail": (self.component_provider_agent.name, self.component_provider_agent.fix),
            }
        )

        self._assert_contracts()
        if self.max_refine < 0:
            raise ValueError(f"max_refine must be >= 0, got {self.max_refine}")

    def run(
        self,
        chapter_request: ChapterRequest,
        dedup_index: IDedupIndex,
    ) -> ChapterResult:
        """
        Return only bundles that pass Layer-1 validation.

        Dropped bundles are counted, not returned. Planner-level top-up handles
        deficits after this result is merged into the assessment buffer.
        """
        request_payload = _dump_model(chapter_request)
        warnings: List[str] = []

        announcement = ChapterAnnouncement(
            chapter_request=request_payload,
            dedup_index_size=len(dedup_index),
        )

        with ChapterMsgHub(announcement):
            retrieve_content = self._reply(
                self.data_retrieve_agent,
                {
                    "chapter_request": request_payload,
                    "dedup_index": dedup_index,
                },
            )
            chunks = _as_list(retrieve_content.get("chunks"))
            sufficient = bool(retrieve_content.get("sufficient", bool(chunks)))

            if not sufficient:
                warnings.append(
                    "DataRetrieveAgent flagged insufficient source chunks "
                    f"for chapter {chapter_request.chapter_id!r}."
                )

            generated_content = self._reply(
                self.subject_generator_agent,
                {
                    "chapter_request": request_payload,
                    "chunks": chunks,
                    "dedup_index": dedup_index,
                },
            )
            raw_bundles = _as_list(generated_content.get("bundles"))

            component_content = self._reply(
                self.component_provider_agent,
                {
                    "chapter_request": request_payload,
                    "chunks": chunks,
                    "bundles": raw_bundles,
                },
            )
            candidate_bundles = _as_list(component_content.get("bundles"))

            passed: List[dict] = []
            dropped_count = 0

            for index, raw_bundle in enumerate(candidate_bundles):
                bundle, warning = self._refine_bundle(
                    raw_bundle=raw_bundle,
                    chapter_request_payload=request_payload,
                    chunks=chunks,
                    dedup_index=dedup_index,
                )

                if bundle is None:
                    dropped_count += 1
                    warnings.append(
                        warning
                        or f"Bundle at index {index} was dropped after refinement."
                    )
                    continue

                passed.append(_dump_model(bundle))
                dedup_index.add(bundle.stem)

        return ChapterResult(
            chapter_id=chapter_request.chapter_id,
            bundles=passed,
            dropped_count=dropped_count,
            sufficient=sufficient,
            warnings=warnings,
        )

    def _refine_bundle(
        self,
        *,
        raw_bundle: Any,
        chapter_request_payload: Dict[str, Any],
        chunks: List[Any],
        dedup_index: IDedupIndex,
    ) -> Tuple[Optional[QABundle], Optional[str]]:
        """
        Validate a single bundle, repairing through its owning agent when needed.

        max_refine is interpreted as "number of repair attempts", so there is an
        initial validation plus at most max_refine revised validations.
        """
        bundle_payload = _copy_mapping(raw_bundle)
        last_verdict: Optional[ValidationVerdict] = None

        for repair_attempt in range(self.max_refine + 1):
            parsed_bundle, guard_verdict = self._run_guard_checks(
                bundle_payload=bundle_payload,
                dedup_index=dedup_index,
            )

            if guard_verdict is None:
                validator_content = self._reply(
                    self.qa_validator_agent,
                    {
                        "bundle": _dump_model(parsed_bundle),
                        "chapter_request": chapter_request_payload,
                        "chunks": chunks,
                        "dedup_index": dedup_index,
                    },
                )
                verdict = ValidationVerdict.from_mapping(validator_content)
            else:
                verdict = guard_verdict

            last_verdict = verdict
            if verdict.passed:
                assert parsed_bundle is not None
                return _stamp_pass(parsed_bundle), None

            if repair_attempt >= self.max_refine:
                break

            route = self.defect_router.resolve(verdict.defect_type)
            if route is None:
                break

            bundle_payload = self._repair_bundle(
                fixer=route.fixer,
                bundle_payload=bundle_payload,
                verdict=verdict,
                owner=route.owner,
                chapter_request_payload=chapter_request_payload,
                chunks=chunks,
            )

        return None, _drop_reason(last_verdict)

    def _run_guard_checks(
        self,
        *,
        bundle_payload: Mapping[str, Any],
        dedup_index: IDedupIndex,
    ) -> Tuple[Optional[QABundle], Optional[ValidationVerdict]]:
        try:
            parsed_bundle = QABundle.model_validate(bundle_payload)
        except Exception as exc:  # Pydantic raises ValidationError at runtime.
            return None, ValidationVerdict(
                passed=False,
                defect_type="schema_invalid",
                defect_detail=str(exc),
            )

        if dedup_index.contains(parsed_bundle.stem):
            return parsed_bundle, ValidationVerdict(
                passed=False,
                defect_type="dedup_fail",
                defect_detail="Question stem already exists in the global dedup index.",
            )

        return parsed_bundle, None

    def _repair_bundle(
        self,
        *,
        fixer: IRepairable,
        bundle_payload: Mapping[str, Any],
        verdict: ValidationVerdict,
        owner: str,
        chapter_request_payload: Dict[str, Any],
        chunks: List[Any],
    ) -> Dict[str, Any]:
        repair_content = _msg_content(
            fixer.fix(
                make_msg(
                    name="team_runner",
                    content={
                        "bundle": dict(bundle_payload),
                        "verdict": verdict.as_content(),
                        "repair_owner": owner,
                        "chapter_request": chapter_request_payload,
                        "chunks": chunks,
                    },
                )
            )
        )
        return _copy_mapping(repair_content.get("bundle", bundle_payload))

    def _reply(self, agent: object, content: Dict[str, Any]) -> Dict[str, Any]:
        return _msg_content(
            agent.reply(make_msg(name="team_runner", content=content))  # type: ignore[attr-defined]
        )

    def _assert_contracts(self) -> None:
        required = {
            "data_retrieve_agent": self.data_retrieve_agent,
            "subject_generator_agent": self.subject_generator_agent,
            "component_provider_agent": self.component_provider_agent,
            "qa_validator_agent": self.qa_validator_agent,
        }
        for label, agent in required.items():
            if not hasattr(agent, "reply"):
                raise TypeError(f"{label} must implement reply().")

        for label, agent in {
            "subject_generator_agent": self.subject_generator_agent,
            "component_provider_agent": self.component_provider_agent,
        }.items():
            if not hasattr(agent, "fix"):
                raise TypeError(f"{label} must implement fix().")


def _msg_content(msg: object) -> Dict[str, Any]:
    content = getattr(msg, "content", None)
    if not isinstance(content, dict):
        raise TypeError(
            "Agent replies must be Msg-like objects with dict content; "
            f"got {type(content).__name__}."
        )
    return content


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    raise TypeError(f"Expected list content from agent, got {type(value).__name__}.")


def _copy_mapping(value: Any) -> Dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError(f"Expected bundle mapping, got {type(value).__name__}.")


def _dump_model(value: Any) -> Dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError(f"Expected mapping-like model, got {type(value).__name__}.")


def _stamp_pass(bundle: QABundle) -> QABundle:
    bundle.validation.layer1 = "pass"
    return bundle


def _drop_reason(verdict: Optional[ValidationVerdict]) -> str:
    if verdict is None:
        return "Bundle was dropped before a validation verdict was produced."

    detail = f": {verdict.defect_detail}" if verdict.defect_detail else ""
    defect = verdict.defect_type or "unknown_defect"
    return f"Bundle dropped after Layer-1 defect {defect!r}{detail}."


def run_chapter_team(
    chapter_request: ChapterRequest,
    dedup_index: IDedupIndex,
    *,
    runner: ChapterTeamRunner,
) -> ChapterResult:
    """Convenience function matching the planner pseudocode in the MVP spec."""
    return runner.run(chapter_request=chapter_request, dedup_index=dedup_index)


__all__ = [
    "DEFAULT_MAX_REFINE",
    "ChapterTeamRunner",
    "ValidationVerdict",
    "run_chapter_team",
]

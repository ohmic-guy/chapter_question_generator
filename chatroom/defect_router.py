"""
chatroom/defect_router.py
─────────────────────────
Routes Layer-1 validation defects to the agent that can repair them.

This is M8 orchestration code. It does not implement any agent's intelligence;
it only owns the deterministic routing table used by ChapterTeamRunner.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping, Optional

from agents.protocols import IComponentProviderAgent, IRepairable, ISubjectGeneratorAgent


GENERATOR_DEFECTS = frozenset(
    {
        "schema_invalid",
        "citation_missing",
        "citation_invalid",
        "consistency",
        "hardness_mismatch",
        "ambiguity",
        "dedup_fail",
        "answer_wrong",
    }
)

COMPONENT_PROVIDER_DEFECTS = frozenset(
    {
        "math_error",
        "formula_invalid",
        "component_missing",
        "sympy_fail",
    }
)


@dataclass(frozen=True)
class RouteDecision:
    """Resolved repair owner for a single validator defect."""

    defect_type: str
    owner: str
    fixer: IRepairable


class DefectRouter:
    """
    Small deterministic dispatch table for the item-refinement loop.

    Unknown defects return None; ChapterTeamRunner drops those bundles instead
    of guessing which agent should repair them.
    """

    def __init__(
        self,
        generator: ISubjectGeneratorAgent,
        component_provider: IComponentProviderAgent,
        extra_routes: Optional[Mapping[str, str]] = None,
    ) -> None:
        routes: Dict[str, str] = {
            **{defect: "generator" for defect in GENERATOR_DEFECTS},
            **{defect: "component_provider" for defect in COMPONENT_PROVIDER_DEFECTS},
        }
        if extra_routes:
            routes.update(extra_routes)

        self._routes = routes
        self._fixers: Dict[str, IRepairable] = {
            "generator": generator,
            "component_provider": component_provider,
        }

    def route(self, defect_type: Optional[str]) -> Optional[RouteDecision]:
        """Return the fixer for defect_type, or None when it is not repairable."""
        if not defect_type:
            return None

        owner = self._routes.get(defect_type)
        if owner is None:
            return None

        fixer = self._fixers.get(owner)
        if fixer is None:
            return None

        return RouteDecision(defect_type=defect_type, owner=owner, fixer=fixer)

    def owner_for(self, defect_type: Optional[str]) -> Optional[str]:
        decision = self.route(defect_type)
        return decision.owner if decision else None


__all__ = [
    "COMPONENT_PROVIDER_DEFECTS",
    "GENERATOR_DEFECTS",
    "DefectRouter",
    "RouteDecision",
]

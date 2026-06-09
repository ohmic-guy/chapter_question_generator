"""
chatroom/defect_router.py
──────────────────────────
Maps validator defect_type strings to the agent fix() callable
responsible for repairing that defect.

SOLID notes
───────────
  OCP  — new defect types are registered via register(); no code change needed.
         The routing table is built in api/container.py (composition root),
         not here and not in team_runner.py.
  SRP  — owns only the routing concern; knows nothing about agents or bundles.
  DIP  — team_runner depends on DefectRouter, not on concrete agent callables.

Consumed by
───────────
  chatroom/team_runner.py  — calls router.resolve(defect_type) per failed bundle
  api/container.py         — constructs and populates the router

DO NOT import anything from this project here. Pure stdlib only.
"""

from __future__ import annotations

import logging
from typing import Callable, Dict, Optional

from agentscope.message import Msg

logger = logging.getLogger(__name__)

# Callable shape every fixer must satisfy (mirrors IRepairable.fix)
FixerFn = Callable[[Msg], Msg]


class DefectRouter:
    """
    Registry that maps a defect_type string → the agent fix() callable
    that knows how to repair it.

    Usage (api/container.py)
    ────────────────────────
        router = DefectRouter({
            "math_error":       component_agent.fix,
            "citation_missing": generator_agent.fix,
            ...
        })

    Extension without code change
    ──────────────────────────────
        router.register("new_defect_type", some_agent.fix)
    """

    def __init__(self, routes: Optional[Dict[str, FixerFn]] = None) -> None:
        self._routes: Dict[str, FixerFn] = dict(routes or {})
        logger.debug("DefectRouter initialised with %d routes", len(self._routes))

    def resolve(self, defect_type: str) -> Optional[FixerFn]:
        """
        Return the fixer for defect_type, or None if unregistered.

        Callers treat None as: drop the bundle immediately (no fix possible).
        """
        fixer = self._routes.get(defect_type)
        if fixer is None:
            logger.warning(
                "DefectRouter: no fixer registered for defect_type=%r — bundle will be dropped",
                defect_type,
            )
        return fixer

    def register(self, defect_type: str, fixer: FixerFn) -> None:
        """
        Add or replace a route at runtime.
        Calling this after ChapterTeamRunner is constructed takes effect
        on the next chapter run (runner holds a reference to this router).
        """
        if defect_type in self._routes:
            logger.info("DefectRouter: replacing existing route for %r", defect_type)
        self._routes[defect_type] = fixer
        logger.debug("DefectRouter: registered fixer for %r", defect_type)

    def registered_types(self) -> list[str]:
        """Return sorted list of all registered defect_type keys."""
        return sorted(self._routes.keys())

    def __repr__(self) -> str:
        return f"DefectRouter(routes={self.registered_types()})"


__all__ = ["FixerFn", "DefectRouter"]
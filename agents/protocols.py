"""
agents/protocols.py
───────────────────
All agent interface contracts for the Chapter Question Generator team.

Design decisions
────────────────
  ISP  — IAgent and IRepairable are separated.
         Only agents that participate in the refinement loop implement IRepairable.
         IDataRetrieveAgent and IQAValidatorAgent are never asked to self-repair.

  DIP  — team_runner.py depends on these Protocols, never on concrete agent classes.

  AgentScope 2.0 — base method is reply(x: Msg) -> Msg.
                   __call__ in AgentBase delegates to reply(); Protocols mirror that.

Consumed by
────────────
  chatroom/team_runner.py   — type hints + _assert_contracts()
  api/container.py          — wiring concrete agents against these interfaces

DO NOT import anything from this project here.
This file must stay dependency-free (pure stdlib + agentscope.message).
"""

from __future__ import annotations

from typing import Optional, Protocol, Sequence, Union, runtime_checkable

try:
    from agentscope.message import Msg
except ModuleNotFoundError:  # pragma: no cover - local fallback for non-AgentScope test envs
    class Msg:  # type: ignore[no-redef]
        """Minimal AgentScope Msg stand-in used only when agentscope is absent."""

        def __init__(self, name: str, content: object, role: str = "assistant") -> None:
            self.name = name
            self.content = content
            self.role = role


# ─────────────────────────────────────────────────────────────────────────────
# Primitives
# ─────────────────────────────────────────────────────────────────────────────

@runtime_checkable
class IAgent(Protocol):
    """
    Minimal contract every agent in this team must satisfy.

    name    — human-readable label; used in hub logs and error messages.
    reply() — AgentScope 2.0's primary dispatch method.
               Signature mirrors AgentBase.reply() exactly so that
               @runtime_checkable isinstance() checks pass for any AgentBase subclass.
               AgentBase.__call__ delegates to reply() + broadcasts to audiences.
    """
    name: str

    def reply(self, x: Optional[Union[Msg, Sequence[Msg]]] = None) -> Msg:
        """Process one incoming message; return one outgoing message."""
        ...


@runtime_checkable
class IRepairable(Protocol):
    """
    Agents that participate in the refinement loop must also implement fix().
    Kept separate from IAgent so non-repairable agents are not forced to stub it.
    """

    def fix(self, x: Optional[Union[Msg, Sequence[Msg]]] = None) -> Msg:
        """
        Repair a single bundle given a failed validation verdict.

        Expected x.content shape:
            {
              "bundle":  dict,   # the Q&A bundle that failed
              "verdict": dict,   # full verdict from QAValidatorAgent
                                 # { passed, defect_type, defect_detail }
            }

        Must return a Msg whose content is:
            { "bundle": dict }   # revised bundle; source_chunk_ids MUST be preserved
        """
        ...


# ─────────────────────────────────────────────────────────────────────────────
# Composed agent protocols
# ─────────────────────────────────────────────────────────────────────────────

@runtime_checkable
class IDataRetrieveAgent(IAgent, Protocol):
    """
    Fetches chapter chunks from storage. No repair responsibility.

    reply() input  (x.content):
        {
          "chapter_request": dict   # ChapterRequest.model_dump()
        }

    reply() output (return.content):
        {
          "chapter_id":  str,
          "chunks":      list[dict],  # text chunks + math-image chunk records
          "chunk_count": int,
          "sufficient":  bool,        # False → runner surfaces warning to Planner
        }
    """
    ...


@runtime_checkable
class ISubjectGeneratorAgent(IAgent, IRepairable, Protocol):
    """
    Generates raw Q&A bundles from retrieved chunks.
    Implements IRepairable — fixes citation, consistency, hardness defects.

    reply() input  (x.content):
        {
          "chapter_request": dict,    # ChapterRequest.model_dump()
          "chunks":          list[dict],
        }

    reply() output (return.content):
        {
          "bundles": list[dict]       # raw bundles; source_chunk_ids REQUIRED on every item
        }

    fix() repairs defects owned by 'generator':
        citation_missing | citation_invalid | consistency |
        hardness_mismatch | ambiguity | dedup_fail | answer_wrong
    """
    ...


@runtime_checkable
class IComponentProviderAgent(IAgent, IRepairable, Protocol):
    """
    Attaches and verifies components (diagrams, formulas, tables, symbols).
    Implements IRepairable — fixes math/formula defects.

    reply() input  (x.content):
        {
          "bundles": list[dict]       # output of SubjectGeneratorAgent
        }

    reply() output (return.content):
        {
          "bundles": list[dict]       # enriched bundles with verified components
        }

    fix() repairs defects owned by 'component_provider':
        math_error | formula_invalid | component_missing | sympy_fail
    """
    ...


@runtime_checkable
class IQAValidatorAgent(IAgent, Protocol):
    """
    Layer-1 exit gate. Validates ONE bundle. No repair responsibility.

    reply() input  (x.content):
        {
          "bundle":          dict,    # single Q&A bundle
          "chapter_request": dict,    # ChapterRequest.model_dump()
        }

    reply() output (return.content):
        {
          "passed":         bool,
          "defect_type":    str | None,
          "defect_detail":  str | None,
        }

    defect_type MUST be one of the keys registered in DefectRouter
    (see chatroom/defect_router.py). Emitting an unregistered string
    causes the bundle to be dropped immediately without a fix attempt.

    Valid defect_type values
    ────────────────────────
    Owned by component_provider:
        math_error | formula_invalid | component_missing | sympy_fail

    Owned by generator:
        citation_missing | citation_invalid | consistency |
        hardness_mismatch | ambiguity | dedup_fail | answer_wrong
    """
    ...


# ─────────────────────────────────────────────────────────────────────────────
# Export list — import * from protocols gives exactly these names
# ─────────────────────────────────────────────────────────────────────────────

__all__ = [
    "IAgent",
    "IRepairable",
    "IDataRetrieveAgent",
    "ISubjectGeneratorAgent",
    "IComponentProviderAgent",
    "IQAValidatorAgent",
]

# chatroom/team_runner.py

from pathlib import Path
import json

from .hub import ChapterHub

from agents.data_retrieve_agent import DataRetrieveAgent
from agents.subject_generator_agent import SubjectGeneratorAgent
from agents.component_provider_agent import ComponentProviderAgent
from agents.qa_validator_agent import QAValidatorAgent

class TeamRunner:

```
def __init__(self):

    config_path = (
        Path(__file__)
        .parent.parent
        / "config"
        / "generator_config.json"
    )

    with open(config_path) as f:
        self.config = json.load(f)

    self.max_refine = (
        self.config["generation"]["max_refine"]
    )

    self.retrieve_agent = DataRetrieveAgent()
    self.generator_agent = SubjectGeneratorAgent()
    self.component_agent = ComponentProviderAgent()
    self.validator_agent = QAValidatorAgent()

def run(
    self,
    chapter_request,
    dedup_index,
):

    agents = [
        self.retrieve_agent,
        self.generator_agent,
        self.component_agent,
        self.validator_agent,
    ]

    with ChapterHub(
        agents=agents,
        chapter_request=chapter_request,
        dedup_index=dedup_index,
    ):

        retrieval_result = (
            self.retrieve_agent.retrieve(
                book_id=chapter_request.book_id,
                chapter_id=chapter_request.chapter_id,
                request=chapter_request,
            )
        )

        chunks = retrieval_result["chunks"]

        bundles = (
            self.generator_agent.generate(
                chapter_request=chapter_request,
                chunks=chunks,
            )
        )

        validated_bundles = []

        for bundle in bundles:

            bundle = (
                self.component_agent
                .attach_components(bundle)
            )

            refined = self._refine_bundle(
                bundle
            )

            if refined:
                validated_bundles.append(
                    refined
                )

        return {
            "chapter_id":
                chapter_request.chapter_id,
            "bundles":
                validated_bundles,
            "deficit":
                len(bundles)
                - len(validated_bundles),
        }

def _refine_bundle(
    self,
    bundle,
):

    for _ in range(self.max_refine):

        verdict = (
            self.validator_agent
            .validate(bundle)
        )

        if verdict["passed"]:

            bundle["validation"] = {
                "layer1": "pass"
            }

            return bundle

        bundle = self._route_fix(
            bundle,
            verdict,
        )

        if bundle is None:
            return None

    return None

def _route_fix(
    self,
    bundle,
    verdict,
):

    reason = verdict["reason"]

    component_reasons = {
        "formula_error",
        "diagram_error",
        "component_missing",
    }

    if reason in component_reasons:

        return (
            self.component_agent.revise(
                bundle,
                verdict,
            )
        )

    return (
        self.generator_agent.revise(
            bundle,
            verdict,
        )
    )
```
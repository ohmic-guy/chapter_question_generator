from agentscope.message import Msg
from agentscope.msghub import msghub

class ChapterHub:

```
def __init__(
    self,
    agents,
    chapter_request,
    dedup_index,
):
    self.agents = agents
    self.chapter_request = chapter_request
    self.dedup_index = dedup_index

def __enter__(self):

    announcement = Msg(
        name="planner",
        role="system",
        content={
            "chapter_request":
                self.chapter_request.model_dump(),
            "dedup_index":
                self.dedup_index,
        },
    )

    self._hub = msghub(
        participants=self.agents,
        announcement=announcement,
    )

    return self._hub.__enter__()

def __exit__(
    self,
    exc_type,
    exc_val,
    exc_tb,
):
    return self._hub.__exit__(
        exc_type,
        exc_val,
        exc_tb,
    )
```

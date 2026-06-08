from typing import Dict, List, Literal

from pydantic import BaseModel, Field

QuestionType = Literal["mcq", "msq", "numerical", "short", "long"]

class QuestionSpec(BaseModel):
type: QuestionType
count: int = Field(gt=0)
marks: int = Field(gt=0)

class DifficultyMix(BaseModel):
easy: int = 0
medium: int = 0
hard: int = 0

class ChapterRequest(BaseModel):
book_id: str
chapter_id: str
subject: str

```
types: List[QuestionSpec]

difficulty: Dict[
    QuestionType,
    DifficultyMix
]
```

from fastapi import FastAPI

from chatroom.team_runner import TeamRunner
from models.chapter_request import ChapterRequest

app = FastAPI()

runner = TeamRunner()

@app.post("/generate-chapter")
async def generate_chapter(
request: ChapterRequest,
):

result = runner.run(
    chapter_request=request,
    dedup_index={},
)

return result
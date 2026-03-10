from pydantic import BaseModel


class ChatRequest(BaseModel):
    query: str
    history: list[dict] = []  # [{"role": "user"|"assistant", "content": "..."}]


class SourceDoc(BaseModel):
    content: str
    metadata: dict = {}


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceDoc] = []

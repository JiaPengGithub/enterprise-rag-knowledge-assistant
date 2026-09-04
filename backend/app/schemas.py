from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=2)
    user_id: str = "hr_user"


class DocumentUpdate(BaseModel):
    title: str | None = None
    department: str | None = None
    roles: list[str] | None = None

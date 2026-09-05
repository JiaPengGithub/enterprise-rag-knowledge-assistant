from typing import Literal

from pydantic import BaseModel, Field


DocumentClassification = Literal["public", "internal", "confidential"]


class ChatRequest(BaseModel):
    question: str = Field(min_length=2)
    user_id: str = "hr_user"


class DocumentUpdate(BaseModel):
    user_id: str = "admin"
    title: str | None = None
    department: str | None = None
    roles: list[str] | None = None
    classification: DocumentClassification | None = None

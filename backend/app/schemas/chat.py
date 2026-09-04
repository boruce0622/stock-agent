from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ConversationCreate(BaseModel):
    title: str = Field(default="新会话", max_length=120)


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    current_symbol: str | None
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    conversation_id: str
    run_id: str | None
    role: str
    content: str
    extra_data: dict
    created_at: datetime


class RunCreate(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    client_request_id: str = Field(min_length=8, max_length=100)


class RunAccepted(BaseModel):
    run_id: str
    conversation_id: str
    status: str
    events_url: str

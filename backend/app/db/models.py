from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


def new_id() -> str:
    return str(uuid.uuid4())


class Conversation(TimestampMixin, Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(120), default="新会话", nullable=False)
    current_symbol: Mapped[str | None] = mapped_column(String(32))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
    runs: Mapped[list[AgentRun]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_conversation_created", "conversation_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="SET NULL"))
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    extra_data: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        Index("ix_runs_conversation_created", "conversation_id", "created_at"),
        Index("ux_runs_idempotency", "conversation_id", "idempotency_key", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), default="queued", nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    conversation: Mapped[Conversation] = relationship(back_populates="runs")
    tool_calls: Mapped[list[ToolCall]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    arguments_redacted: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    source: Mapped[str | None] = mapped_column(String(64))
    data_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    run: Mapped[AgentRun] = relationship(back_populates="tool_calls")


class AIConfiguration(TimestampMixin, Base):
    __tablename__ = "ai_configurations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default="default")
    provider: Mapped[str] = mapped_column(String(32), default="openai", nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(500))
    api_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)


class MarketDataConfiguration(TimestampMixin, Base):
    __tablename__ = "market_data_configurations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default="default")
    provider: Mapped[str] = mapped_column(String(32), default="hybrid", nullable=False)
    credential_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)

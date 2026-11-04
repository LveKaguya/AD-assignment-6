"""Validated knowledge base document and embedded source metadata."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.common import MongoModel, NonEmptyText, utc_now


class SourceMetadata(BaseModel):
    source_type: NonEmptyText
    source_uri: NonEmptyText
    section: NonEmptyText | None = None
    page: int | None = Field(default=None, ge=1)


class KnowledgeBaseItem(MongoModel):
    title: NonEmptyText
    description: NonEmptyText
    content: NonEmptyText
    category: NonEmptyText
    document_type: NonEmptyText
    product: NonEmptyText
    version: NonEmptyText | None = None
    tags: list[NonEmptyText] = Field(default_factory=list)
    source: SourceMetadata
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    deleted_at: datetime | None = None

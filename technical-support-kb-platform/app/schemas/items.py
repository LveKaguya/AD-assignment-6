"""Validated catalog requests and public responses."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.models.common import NonEmptyText
from app.models.kb_item import KnowledgeBaseItem, SourceMetadata

Category = Literal[
    "Networking",
    "Operating Systems",
    "Database Systems",
    "Deployment and DevOps",
    "Security",
]
DocumentType = Literal[
    "troubleshooting guide", "FAQ", "configuration manual", "release notes"
]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=200)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=1000)]
Content = Annotated[str, StringConstraints(strip_whitespace=True, min_length=20)]


class SourceInput(SourceMetadata):
    model_config = ConfigDict(extra="forbid")


class ItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title
    description: Description
    content: Content
    category: Category
    document_type: DocumentType
    product: NonEmptyText
    version: NonEmptyText | None = None
    tags: list[NonEmptyText] = Field(default_factory=list)
    source: SourceInput


class ItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title | None = None
    description: Description | None = None
    content: Content | None = None
    category: Category | None = None
    document_type: DocumentType | None = None
    product: NonEmptyText | None = None
    version: NonEmptyText | None = None
    tags: list[NonEmptyText] | None = None
    source: SourceInput | None = None

    @model_validator(mode="after")
    def validate_update(self) -> "ItemUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one item field is required")
        if any(
            getattr(self, field) is None
            for field in self.model_fields_set
            if field != "version"
        ):
            raise ValueError("Only version may be set to null")
        return self


class ItemResponse(BaseModel):
    id: str
    title: str
    description: str
    content: str
    category: str
    document_type: str
    product: str
    version: str | None
    tags: list[str]
    source: SourceMetadata
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None

    @classmethod
    def from_item(cls, item: KnowledgeBaseItem) -> "ItemResponse":
        return cls(
            id=str(item.id),
            title=item.title,
            description=item.description,
            content=item.content,
            category=item.category,
            document_type=item.document_type,
            product=item.product,
            version=item.version,
            tags=item.tags,
            source=item.source,
            created_at=item.created_at,
            updated_at=item.updated_at,
            deleted_at=item.deleted_at,
        )


class ItemPage(BaseModel):
    items: list[ItemResponse]
    total: int
    skip: int
    limit: int


class SearchHit(ItemResponse):
    relevance_score: float | None

    @classmethod
    def from_item_and_score(
        cls, item: KnowledgeBaseItem, score: float | None
    ) -> "SearchHit":
        return cls(**ItemResponse.from_item(item).model_dump(), relevance_score=score)


class SearchPage(BaseModel):
    items: list[SearchHit]
    total: int
    skip: int
    limit: int

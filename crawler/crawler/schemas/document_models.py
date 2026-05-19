# crawler/schemas/document_models.py

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RawDocumentBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc_id: str
    source_type: str
    page_kind: str
    department: str | None = None

    title: str = ""
    source_url: str
    published_at: str | None = None
    updated_at: str | None = None

    raw_text: str = ""
    normalize: str | None = None
    table_text: str = ""
    attachment_text: str | None = None
    structured_sections: list[dict] = Field(default_factory=list)

    version: int = 1
    change_type: str | None = None
    collected_at: str

    content_hash: str
    html: str
    metadata: dict = Field(default_factory=dict)


class BoardDetailRawDocument(RawDocumentBase):
    page_kind: Literal["board_detail"] = "board_detail"

    views: int | None = None
    image_urls: list[str] = Field(default_factory=list)
    image_texts: list[dict] = Field(default_factory=list)
    attachments: list[dict] = Field(default_factory=list)


class StaticPageRawDocument(RawDocumentBase):
    page_kind: Literal["static_page"] = "static_page"

    views: int | None = None
    image_urls: list[str] = Field(default_factory=list)
    image_texts: list[dict] = Field(default_factory=list)
    attachments: list[dict] = Field(default_factory=list)
    outgoing_links: list[str] = Field(default_factory=list)


class CuratedDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc_id: str
    source_type: str
    page_kind: str
    department: str | None = None

    title: str = ""
    source_url: str
    published_at: str | None = None
    updated_at: str | None = None

    raw_text: str = ""
    normalize: str = ""
    table_text: str = ""
    attachment_text: str | None = None
    image_text: str | None = None
    structured_sections: list[dict] = Field(default_factory=list)

    version: int = 1
    change_type: str | None = None
    collected_at: str

    content_hash: str
    metadata: dict = Field(default_factory=dict)

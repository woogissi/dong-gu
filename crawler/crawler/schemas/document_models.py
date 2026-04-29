# crawler/schemas/document_models.py

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, ConfigDict


class RawDocumentBase(BaseModel):
    model_config = ConfigDict(extra="forbid")       # 정의되지않은 필드 들어오면 에러

    doc_id: str                             # 문서 고유 ID
    parent_doc_id: str | None = None        # 부모 문서 ID
    source_type: str                        # notice / academic_notice / library 등
    page_kind: str                          # 게시판/정적 페이지

    category_lv1: str | None = None         # 예)대학생활
    category_lv2: str | None = None         # 예)도서관
    department: str | None = None           # 작성자/부서

    title: str = ""                         # 제목
    summary: str | None = None              # 요약
    source_url: str                         # URL

    published_at: str | None = None         # 작성일
    updated_at: str | None = None           # 수정일
    valid_from: str | None = None           # 기간(예: 수강신청 시작일)
    valid_to: str | None = None             # 예: 수강신청 종료일

    target_audience: list[str] = Field(default_factory=list)    # 대상
    keywords: list[str] = Field(default_factory=list)           # 키워드

    raw_text: str = ""             
    normalize: str | None = None
    table_text: str = ""
    attachment_text: str | None = None

    language: str = "ko"
    status: str = "active"
    version: int = 1
    collected_at: str

    content_hash: str
    html: str


class BoardDetailRawDocument(RawDocumentBase):
    page_kind: Literal["board_detail"] = "board_detail"

    views: int | None = None                                # 조회수
    image_urls: list[str] = Field(default_factory=list)     # 이미지 url
    image_texts: list[dict] = Field(default_factory=list)
    attachments: list[dict] = Field(default_factory=list)   # 첨부파일


class StaticPageRawDocument(RawDocumentBase):
    page_kind: Literal["static_page"] = "static_page"

    views: int | None = None
    image_urls: list[str] = Field(default_factory=list)
    image_texts: list[dict] = Field(default_factory=list)
    attachments: list[dict] = Field(default_factory=list)
    outgoing_links: list[str] = Field(default_factory=list)     # 내부링크


class CuratedDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc_id: str
    parent_doc_id: str | None = None
    university: str = "동의대학교"
    campus: str | None = None
    source_type: str
    page_kind: str

    category_lv1: str | None = None
    category_lv2: str | None = None
    department: str | None = None

    title: str = ""
    summary: str | None = None
    source_url: str

    published_at: str | None = None
    updated_at: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None

    target_audience: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)

    raw_text: str = ""
    normalize: str = ""
    table_text: str = ""
    attachment_text: str | None = None
    image_text: str | None = None

    language: str = "ko"
    status: str = "active"
    version: int = 1
    collected_at: str

    content_hash: str
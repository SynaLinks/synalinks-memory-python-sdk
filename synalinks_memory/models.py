"""Pydantic response models for the Synalinks Memory API."""

from typing import Any

from pydantic import BaseModel


class PredicateInfo(BaseModel):
    """A single predicate (table, concept, or rule)."""

    name: str
    description: str = ""


class PredicateList(BaseModel):
    """Response from GET /v1/predicates."""

    tables: list[PredicateInfo] = []
    concepts: list[PredicateInfo] = []
    rules: list[PredicateInfo] = []


class Column(BaseModel):
    """Column metadata returned alongside query results."""

    name: str
    json_schema: dict[str, Any] = {}


class ExecuteResult(BaseModel):
    """Response from POST /v1/predicates/{name}/execute."""

    predicate: str
    columns: list[Column]
    rows: list[dict[str, Any]]
    row_count: int
    total_rows: int
    offset: int
    limit: int


class SearchResult(BaseModel):
    """Response from POST /v1/predicates/{name}/search."""

    predicate: str
    keywords: str
    columns: list[Column]
    rows: list[dict[str, Any]]
    row_count: int
    total_rows: int
    offset: int
    limit: int


class UploadResult(BaseModel):
    """Response from POST /v1/tables/upload."""

    predicate: str
    columns: list[Column]
    row_count: int

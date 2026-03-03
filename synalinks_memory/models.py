# License Apache 2.0: (c) 2026 Yoan Sallami (Synalinks Team)

"""Pydantic models for API request and response payloads."""

from typing import Any

from pydantic import BaseModel, ConfigDict


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
    """Response from POST /v1/predicates/{name}/execute.

    ``rows`` uses arbitrary_types_allowed so Pydantic passes the
    already-deserialized list[dict] through without re-validating
    every cell — critical for large result sets.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    predicate: str
    columns: list[Column]
    rows: Any  # list[dict[str, Any]] — skip per-row validation
    row_count: int
    total_rows: int
    offset: int
    limit: int


class SearchResult(BaseModel):
    """Response from POST /v1/predicates/{name}/search.

    See ``ExecuteResult`` for the ``rows`` optimisation rationale.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    predicate: str
    keywords: str
    columns: list[Column]
    rows: Any  # list[dict[str, Any]] — skip per-row validation
    row_count: int
    total_rows: int
    offset: int
    limit: int


class UploadResult(BaseModel):
    """Response from POST /v1/tables/upload."""

    predicate: str
    columns: list[Column]
    row_count: int


class InsertResult(BaseModel):
    """Response from POST /v1/predicates/{name}/rows."""

    predicate: str
    row: dict[str, Any]


class UpdateResult(BaseModel):
    """Response from PUT /v1/predicates/{name}/rows."""

    predicate: str
    updated_count: int
    values: dict[str, Any]


class ChatStepEvent(BaseModel):
    """A step event emitted during agent processing."""

    step: int
    name: str = ""
    label: str


class ChatAnswerEvent(BaseModel):
    """The final answer event from the agent."""

    answer: str
    messages: list[dict[str, Any]] = []

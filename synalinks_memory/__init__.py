# License Apache 2.0: (c) 2026 Yoan Sallami (Synalinks Team)

"""Synalinks Memory Python SDK — public API surface and re-exports."""

from .version import __version__, version
from .client import SynalinksMemory
from .exceptions import (
    AuthenticationError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
    SynalinksError,
    ValidationError,
)
from .models import ChatAnswerEvent, ChatStepEvent, Column, ExecuteResult, InsertResult, PredicateInfo, PredicateList, SearchResult, UpdateResult, UploadResult


__all__ = [
    "__version__",
    "version",
    "ChatAnswerEvent",
    "ChatStepEvent",
    "AuthenticationError",
    "Column",
    "ExecuteResult",
    "ForbiddenError",
    "InsertResult",
    "NotFoundError",
    "PredicateInfo",
    "PredicateList",
    "RateLimitError",
    "SearchResult",
    "SynalinksError",
    "SynalinksMemory",
    "UpdateResult",
    "UploadResult",
    "ValidationError",
]

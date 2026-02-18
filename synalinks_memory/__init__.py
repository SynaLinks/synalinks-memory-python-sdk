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
from .models import AskAnswerEvent, AskStepEvent, Column, ExecuteResult, PredicateInfo, PredicateList, SearchResult, UploadResult


__all__ = [
    "__version__",
    "version",
    "AskAnswerEvent",
    "AskStepEvent",
    "AuthenticationError",
    "Column",
    "ExecuteResult",
    "ForbiddenError",
    "NotFoundError",
    "PredicateInfo",
    "PredicateList",
    "RateLimitError",
    "SearchResult",
    "SynalinksError",
    "SynalinksMemory",
    "UploadResult",
    "ValidationError",
]

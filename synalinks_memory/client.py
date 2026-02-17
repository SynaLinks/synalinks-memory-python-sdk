"""Synchronous client for the Synalinks Memory API."""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

import httpx

from .exceptions import (
    AuthenticationError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
    SynalinksError,
    ValidationError,
)
from .models import ExecuteResult, PredicateList, SearchResult, UploadResult

_ERROR_MAP: dict[int, type[SynalinksError]] = {
    401: AuthenticationError,
    403: ForbiddenError,
    404: NotFoundError,
    429: RateLimitError,
    400: ValidationError,
}


DEFAULT_BASE_URL = "https://app.synalinks.com/api"


class SynalinksMemory:
    """Synchronous client for the Synalinks Memory API.

    Usage::

        client = SynalinksMemory()  # reads SYNALINKS_API_KEY from env
        predicates = client.list_predicates()
        result = client.execute("MyTable", limit=10)
        client.close()

    Or as a context manager::

        with SynalinksMemory() as client:
            predicates = client.list_predicates()
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
    ) -> None:
        resolved_key = api_key or os.environ.get("SYNALINKS_API_KEY")
        if not resolved_key:
            raise AuthenticationError(
                code="missing_api_key",
                message=(
                    "No API key provided. Pass api_key= or set the "
                    "SYNALINKS_API_KEY environment variable."
                ),
            )
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"X-API-Key": resolved_key},
            timeout=timeout,
        )

        # Fire a non-blocking request to wake up the backend (handles cold start)
        self._warm_up()

    # -- Warm-up ---------------------------------------------------------------

    def _warm_up(self) -> None:
        """Send a background health check to wake up the backend container."""

        def _ping() -> None:
            try:
                self._client.get("/v1/health")
            except Exception:
                logging.getLogger(__name__).debug(
                    "Warm-up request failed (backend may be starting)"
                )

        thread = threading.Thread(target=_ping, daemon=True)
        thread.start()

    # -- Context manager -------------------------------------------------------

    def __enter__(self) -> SynalinksMemory:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    # -- Public API ------------------------------------------------------------

    def list_predicates(self) -> PredicateList:
        """List all available predicates (tables, concepts, rules)."""
        resp = self._client.get("/v1/predicates")
        self._handle_response(resp)
        return PredicateList.model_validate(resp.json())

    def execute(
        self,
        predicate: str,
        *,
        limit: int = 100,
        offset: int = 0,
        format: str | None = None,
        output: str | None = None,
    ) -> ExecuteResult | bytes:
        """Execute a predicate and return rows.

        Args:
            predicate: The predicate name to execute.
            limit: Max rows to return (1–1000).
            offset: Row offset for pagination.
            format: If set to ``json``, ``csv``, or ``parquet``, returns raw
                file bytes instead of an ``ExecuteResult``.
            output: Write the file bytes to this path (only used with *format*).

        Returns:
            ``ExecuteResult`` when *format* is None, otherwise raw ``bytes``.
        """
        body: dict[str, Any] = {"limit": limit, "offset": offset}
        if format is not None:
            body["format"] = format

        resp = self._client.post(
            f"/v1/predicates/{predicate}/execute",
            json=body,
        )
        self._handle_response(resp)

        if format is not None:
            data = resp.content
            if output:
                with open(output, "wb") as f:
                    f.write(data)
            return data

        return ExecuteResult.model_validate(resp.json())

    def search(
        self, predicate: str, keywords: str, *, limit: int = 100, offset: int = 0
    ) -> SearchResult:
        """Search a predicate by keywords."""
        resp = self._client.post(
            f"/v1/predicates/{predicate}/search",
            json={"keywords": keywords, "limit": limit, "offset": offset},
        )
        self._handle_response(resp)
        return SearchResult.model_validate(resp.json())

    def upload(
        self,
        file_path: str,
        *,
        name: str | None = None,
        description: str | None = None,
        overwrite: bool = False,
    ) -> UploadResult:
        """Upload a CSV or Parquet file as a new table.

        Args:
            file_path: Local path to a .csv or .parquet file.
            name: Optional predicate name (CamelCase). Derived from filename if omitted.
            description: Optional table description.
            overwrite: If True, replace an existing table with the same name.

        Returns:
            UploadResult with predicate name, columns, and row count.
        """
        import os as _os

        with open(file_path, "rb") as f:
            files = {"file": (_os.path.basename(file_path), f)}
            data: dict[str, str] = {}
            if name is not None:
                data["name"] = name
            if description is not None:
                data["description"] = description
            if overwrite:
                data["overwrite"] = "true"

            resp = self._client.post("/v1/tables/upload", files=files, data=data)

        self._handle_response(resp)
        return UploadResult.model_validate(resp.json())

    def ask(self, question: str) -> str:
        """Ask the Synalinks agent a question and get a single-turn answer.

        Args:
            question: The question to ask.

        Returns:
            The agent's answer as a string.
        """
        resp = self._client.post("/v1/ask", json={"question": question})
        self._handle_response(resp)
        return resp.json()["answer"]

    # -- Internals -------------------------------------------------------------

    @staticmethod
    def _handle_response(resp: httpx.Response) -> None:
        """Raise a typed exception for non-2xx responses."""
        if resp.is_success:
            return

        # Try to parse the structured error envelope
        code = "unknown"
        message = resp.text
        try:
            body = resp.json()
            error = body.get("error", {})
            code = error.get("code", code)
            message = error.get("message", message)
        except Exception:
            pass

        # Handle 429 specially for retry_after
        if resp.status_code == 429:
            retry_after_raw = resp.headers.get("Retry-After")
            retry_after = float(retry_after_raw) if retry_after_raw else None
            raise RateLimitError(code=code, message=message, retry_after=retry_after)

        exc_cls = _ERROR_MAP.get(resp.status_code, SynalinksError)
        if exc_cls is SynalinksError:
            raise SynalinksError(resp.status_code, code, message)
        raise exc_cls(code=code, message=message)

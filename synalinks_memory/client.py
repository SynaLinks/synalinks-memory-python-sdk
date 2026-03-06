# License Apache 2.0: (c) 2026 Yoan Sallami (Synalinks Team)

"""Synchronous HTTP client for the Synalinks Memory API."""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
    wait_fixed,
    wait_combine,
)

try:
    import orjson as _json

    def _loads(data: bytes | str) -> Any:
        return _json.loads(data)
except ModuleNotFoundError:
    import json as _json  # type: ignore[no-redef]

    def _loads(data: bytes | str) -> Any:  # type: ignore[misc]
        return _json.loads(data)

from .exceptions import (
    AuthenticationError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
    SynalinksError,
    ValidationError,
)
from .models import ChatAnswerEvent, ChatStepEvent, ExecuteResult, InsertResult, PredicateList, SearchResult, UpdateResult, UploadResult

_ERROR_MAP: dict[int, type[SynalinksError]] = {
    401: AuthenticationError,
    403: ForbiddenError,
    404: NotFoundError,
    429: RateLimitError,
    400: ValidationError,
}


DEFAULT_BASE_URL = "https://app.synalinks.com/api"

logger = logging.getLogger(__name__)


def _before_sleep(retry_state) -> None:
    """Log retries, but silently handle rate limits."""
    exc = retry_state.outcome.exception()
    if isinstance(exc, RateLimitError):
        return
    logger.warning(
        "Retrying %s in %.1fs (attempt %d) due to %s",
        retry_state.fn.__qualname__ if retry_state.fn else "call",
        retry_state.next_action.sleep,
        retry_state.attempt_number,
        exc,
    )


def _is_retryable(exc: BaseException) -> bool:
    """Return True for transient errors that are safe to retry.

    Timeouts are excluded — they typically mean the server genuinely
    couldn't respond in time (e.g. a long-running chat), so retrying
    would just waste time.
    """
    if isinstance(exc, httpx.TimeoutException):
        return False
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, RateLimitError):
        return True
    if isinstance(exc, SynalinksError) and exc.status_code >= 500:
        return True
    return False


def _rate_limit_wait(retry_state) -> float:
    """If the last exception was a RateLimitError, use retry_after or a sensible default."""
    exc = retry_state.outcome.exception()
    if isinstance(exc, RateLimitError):
        if exc.retry_after is not None:
            return exc.retry_after
        # No Retry-After header — use a conservative default
        return 1.0
    return 0


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
        timeout: float = 120.0,
        max_retries: int = 3,
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
        # Conversation history for multi-turn chat
        self._messages: list[dict[str, Any]] = []

        # Build the tenacity retryer once and share across all methods
        self._retryer = retry(
            retry=retry_if_exception(_is_retryable),
            stop=stop_after_attempt(max_retries),
            wait=wait_combine(
                wait_fixed(0) + wait_exponential(multiplier=0.5, max=30),
                _rate_limit_wait,
            ),
            before_sleep=_before_sleep,
            reraise=True,
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

    # -- Retryable request helpers ---------------------------------------------

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Send an HTTP request with automatic retries on transient errors."""

        def _do() -> httpx.Response:
            resp = self._client.request(method, url, **kwargs)
            self._handle_response(resp)
            return resp

        return self._retryer(_do)()

    # -- Public API ------------------------------------------------------------

    def list(self) -> PredicateList:
        """List all available predicates (tables, concepts, rules)."""
        resp = self._request("GET", "/v1/predicates")
        return PredicateList.model_validate(_loads(resp.content))

    def execute(
        self,
        predicate: str,
        *,
        limit: int = 100,
        offset: int = 0,
        format: str | None = None,
        output: str | None = None,
    ) -> ExecuteResult | bytes | int:
        """Execute a predicate and return rows.

        Args:
            predicate: The predicate name to execute.
            limit: Max rows to return (1–1000).
            offset: Row offset for pagination.
            format: If set to ``json``, ``csv``, or ``parquet``, returns raw
                file bytes instead of an ``ExecuteResult``.
            output: Write the file bytes to this path (only used with *format*).
                When provided, the response is streamed directly to disk to
                avoid buffering large exports in memory, and the return value
                is the number of bytes written.

        Returns:
            ``ExecuteResult`` when *format* is None; the number of bytes
            written (``int``) when both *format* and *output* are set;
            raw ``bytes`` when only *format* is set.
        """
        body: dict[str, Any] = {"limit": limit, "offset": offset}
        if format is not None:
            body["format"] = format

        if format is not None and output:
            # Stream directly to disk — avoids buffering the entire file.
            # Retries are handled by wrapping the whole streaming block.
            def _stream_to_disk() -> int:
                with self._client.stream(
                    "POST",
                    f"/v1/predicates/{predicate}/execute",
                    json=body,
                ) as stream:
                    self._handle_response(stream)
                    written = 0
                    with open(output, "wb") as f:
                        for chunk in stream.iter_bytes(chunk_size=65_536):
                            f.write(chunk)
                            written += len(chunk)
                    return written

            return self._retryer(_stream_to_disk)()

        resp = self._request("POST", f"/v1/predicates/{predicate}/execute", json=body)

        if format is not None:
            return resp.content

        return ExecuteResult.model_validate(_loads(resp.content))

    def search(
        self, predicate: str, keywords: str, *, limit: int = 100, offset: int = 0
    ) -> SearchResult:
        """Search a predicate by keywords."""
        resp = self._request(
            "POST",
            f"/v1/predicates/{predicate}/search",
            json={"keywords": keywords, "limit": limit, "offset": offset},
        )
        return SearchResult.model_validate(_loads(resp.content))

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

        def _do_upload() -> httpx.Response:
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
            return resp

        resp = self._retryer(_do_upload)()
        return UploadResult.model_validate(_loads(resp.content))

    def insert(self, predicate: str, row: dict[str, Any]) -> InsertResult:
        """Insert a single row into a table.

        Args:
            predicate: The table predicate name.
            row: Column name → value mapping for the new row.

        Returns:
            InsertResult with the predicate name and inserted row.
        """
        resp = self._request(
            "POST",
            f"/v1/predicates/{predicate}/rows",
            json={"row": row},
        )
        return InsertResult.model_validate(_loads(resp.content))

    def update(
        self, predicate: str, filter: dict[str, Any], values: dict[str, Any]
    ) -> UpdateResult:
        """Update rows in a table that match the given filter.

        Args:
            predicate: The table predicate name.
            filter: Column→value conditions for the WHERE clause (ANDed).
            values: Column→new value pairs to SET on matching rows.

        Returns:
            UpdateResult with predicate name, updated count, and values.
        """
        resp = self._request(
            "PUT",
            f"/v1/predicates/{predicate}/rows",
            json={"filter": filter, "values": values},
        )
        return UpdateResult.model_validate(_loads(resp.content))

    def chat(self, question: str) -> str:
        """Send a message to the Synalinks agent and get an answer.

        Conversation history is maintained automatically. Each call appends
        the new exchange to the internal history so follow-up questions have
        full context. Use :meth:`clear` to reset the conversation.

        Args:
            question: The question to ask.

        Returns:
            The agent's answer as a string.
        """
        answer = ""
        for event in self.chat_stream(question):
            if isinstance(event, ChatAnswerEvent):
                answer = event.answer
        return answer

    def chat_stream(self, question: str):
        """Send a message and yield events as they arrive (streaming).

        The ``/v1/chat`` endpoint returns a Server-Sent Events stream. This
        method yields :class:`ChatStepEvent` for each intermediate tool call
        and a final :class:`ChatAnswerEvent` with the agent's answer.

        Conversation history is sent automatically and updated from the
        response so follow-up calls carry full context.

        Args:
            question: The question to ask.

        Yields:
            ``ChatStepEvent`` or ``ChatAnswerEvent`` instances.
        """
        # Build the full message list: prior history + new user message
        outgoing = [*self._messages, {"role": "user", "content": question}]

        # For streaming, collect events via retry then yield them.
        # We cannot yield inside a tenacity-wrapped function, so we
        # collect into a list on each attempt and return it.
        def _do_stream() -> list:
            events: list = []
            with self._client.stream(
                "POST",
                "/v1/chat",
                json={"messages": outgoing},
                headers={"Accept": "text/event-stream"},
                timeout=httpx.Timeout(120.0, read=600.0),
            ) as stream:
                self._handle_response(stream)
                event_type = ""
                data_buf = ""
                for line in stream.iter_lines():
                    if line.startswith("event:"):
                        event_type = line[len("event:"):].strip()
                    elif line.startswith("data:"):
                        data_buf = line[len("data:"):].strip()
                    elif line == "":
                        events.extend(self._process_sse_event(event_type, data_buf))
                        event_type = ""
                        data_buf = ""
                # Handle final event if stream ends without trailing blank line
                events.extend(self._process_sse_event(event_type, data_buf))
            return events

        yield from self._retryer(_do_stream)()

    def clear(self) -> None:
        """Reset the conversation history.

        After calling this, the next :meth:`chat` call starts a fresh
        conversation with no prior context.
        """
        self._messages = []

    def _process_sse_event(self, event_type: str, data_buf: str):
        """Parse a single SSE event and yield the appropriate model."""
        if not data_buf:
            return
        payload = _loads(data_buf)
        if event_type == "step":
            yield ChatStepEvent(**payload)
        elif event_type == "answer":
            event = ChatAnswerEvent(**payload)
            # Update internal conversation history from the server response
            if event.messages:
                self._messages = event.messages
            yield event
        elif event_type == "error":
            raise SynalinksError(
                500,
                "agent_error",
                payload.get("message", "Agent returned an error"),
            )

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
            body = _loads(resp.content)
            error = body.get("error", {})
            code = error.get("code", code)
            message = error.get("message", body.get("detail", message))
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

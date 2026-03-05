"""Unit tests for the Synalinks Memory SDK using httpx MockTransport."""

import json
import logging

import httpx
import pytest
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
    wait_fixed,
    wait_combine,
    before_sleep_log,
)

from synalinks_memory import (
    AuthenticationError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
    SynalinksError,
    SynalinksMemory,
    ValidationError,
)
from synalinks_memory.client import _is_retryable, _rate_limit_wait


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

PREDICATES_RESPONSE = {
    "tables": [
        {"name": "Users", "description": "User accounts"},
        {"name": "Orders", "description": "Order history"},
    ],
    "concepts": [{"name": "ActiveUsers", "description": "Users active in last 30d"}],
    "rules": [{"name": "HighValueOrders", "description": "Orders > $100"}],
}

EXECUTE_RESPONSE = {
    "predicate": "Users",
    "columns": [
        {"name": "id", "json_schema": {"type": "integer"}},
        {"name": "name", "json_schema": {"type": "string"}},
    ],
    "rows": [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"},
    ],
    "row_count": 2,
    "total_rows": 50,
    "offset": 0,
    "limit": 100,
}

SEARCH_RESPONSE = {
    "predicate": "Users",
    "keywords": "alice",
    "columns": [
        {"name": "id", "json_schema": {"type": "integer"}},
        {"name": "name", "json_schema": {"type": "string"}},
    ],
    "rows": [{"id": 1, "name": "Alice"}],
    "row_count": 1,
    "total_rows": 1,
    "offset": 0,
    "limit": 100,
}


def _make_transport(handler):
    """Wrap a handler function into an httpx.MockTransport."""
    return httpx.MockTransport(handler)


_logger = logging.getLogger("synalinks_memory")


def _make_test_retryer(max_retries: int = 1):
    """Build a tenacity retryer for tests. max_retries=1 means no retry."""
    return retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(max_retries),
        wait=wait_combine(
            wait_fixed(0) + wait_exponential(multiplier=0.5, max=30),
            _rate_limit_wait,
        ),
        before_sleep=before_sleep_log(_logger, logging.WARNING),
        reraise=True,
    )


def _make_test_client(transport, base_url="https://api.test", max_retries=1):
    """Create a SynalinksMemory with a mock transport, bypassing __init__."""
    client = SynalinksMemory.__new__(SynalinksMemory)
    client._client = httpx.Client(
        transport=transport, base_url=base_url,
        headers={"X-API-Key": "test-key"},
    )
    client._messages = []
    client._retryer = _make_test_retryer(max_retries)
    return client


def _error_response(status_code: int, code: str, message: str, headers=None):
    body = {"error": {"code": code, "message": message}}
    return httpx.Response(
        status_code,
        json=body,
        headers=headers,
    )


# ---------------------------------------------------------------------------
# Tests — happy path
# ---------------------------------------------------------------------------


class TestListPredicates:
    def test_returns_predicate_list(self):
        def handler(request: httpx.Request):
            assert request.url.path == "/v1/predicates"
            assert request.headers["X-API-Key"] == "test-key"
            return httpx.Response(200, json=PREDICATES_RESPONSE)

        client = _make_test_client(_make_transport(handler))
        result = client.list()

        assert len(result.tables) == 2
        assert result.tables[0].name == "Users"
        assert len(result.concepts) == 1
        assert result.concepts[0].name == "ActiveUsers"
        assert len(result.rules) == 1
        assert result.rules[0].name == "HighValueOrders"


class TestExecute:
    def test_returns_execute_result(self):
        def handler(request: httpx.Request):
            assert request.url.path == "/v1/predicates/Users/execute"
            body = json.loads(request.content)
            assert body["limit"] == 10
            assert body["offset"] == 5
            return httpx.Response(200, json=EXECUTE_RESPONSE)

        client = _make_test_client(_make_transport(handler))
        result = client.execute("Users", limit=10, offset=5)

        assert result.predicate == "Users"
        assert result.row_count == 2
        assert result.total_rows == 50
        assert len(result.columns) == 2
        assert result.columns[0].name == "id"
        assert result.columns[0].json_schema == {"type": "integer"}
        assert result.rows[0]["name"] == "Alice"


class TestSearch:
    def test_returns_search_result(self):
        def handler(request: httpx.Request):
            assert request.url.path == "/v1/predicates/Users/search"
            body = json.loads(request.content)
            assert body["keywords"] == "alice"
            return httpx.Response(200, json=SEARCH_RESPONSE)

        client = _make_test_client(_make_transport(handler))
        result = client.search("Users", "alice")

        assert result.predicate == "Users"
        assert result.keywords == "alice"
        assert result.row_count == 1
        assert result.rows[0]["name"] == "Alice"


# ---------------------------------------------------------------------------
# Tests — error handling
# ---------------------------------------------------------------------------


class TestErrorMapping:
    def _make_client(self, status_code, code, message, headers=None):
        def handler(request: httpx.Request):
            return _error_response(status_code, code, message, headers)

        # max_retries=1 for non-retryable errors (4xx), but 429/5xx are retryable
        # so we still use 1 to avoid slow tests
        return _make_test_client(_make_transport(handler), max_retries=1)

    def test_401_raises_authentication_error(self):
        client = self._make_client(401, "unauthorized", "Invalid API key")
        with pytest.raises(AuthenticationError) as exc_info:
            client.list()
        assert exc_info.value.status_code == 401
        assert exc_info.value.code == "unauthorized"

    def test_403_raises_forbidden_error(self):
        client = self._make_client(403, "forbidden", "Access denied")
        with pytest.raises(ForbiddenError) as exc_info:
            client.list()
        assert exc_info.value.status_code == 403

    def test_404_raises_not_found_error(self):
        client = self._make_client(404, "not_found", "Predicate not found")
        with pytest.raises(NotFoundError) as exc_info:
            client.execute("NonExistent")
        assert exc_info.value.message == "Predicate not found"

    def test_429_raises_rate_limit_error_with_retry_after(self):
        client = self._make_client(
            429, "rate_limit_exceeded", "Too many requests",
            headers={"Retry-After": "1"},
        )
        with pytest.raises(RateLimitError) as exc_info:
            client.list()
        assert exc_info.value.retry_after == 1.0

    def test_400_raises_validation_error(self):
        client = self._make_client(400, "execution_error", "Bad predicate")
        with pytest.raises(ValidationError) as exc_info:
            client.execute("BadPred")
        assert exc_info.value.code == "execution_error"


# ---------------------------------------------------------------------------
# Tests — context manager
# ---------------------------------------------------------------------------


class TestContextManager:
    def test_context_manager(self):
        def handler(request: httpx.Request):
            return httpx.Response(200, json=PREDICATES_RESPONSE)

        transport = _make_transport(handler)

        with SynalinksMemory(api_key="test-key", base_url="https://api.test") as client:
            client._client = httpx.Client(
                transport=transport,
                base_url="https://api.test",
                headers={"X-API-Key": "test-key"},
            )
            result = client.list()
            assert len(result.tables) == 2


# ---------------------------------------------------------------------------
# Tests — retry behaviour
# ---------------------------------------------------------------------------


class TestRetry:
    def test_retries_on_500_then_succeeds(self):
        call_count = 0

        def handler(request: httpx.Request):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _error_response(500, "internal", "Server error")
            return httpx.Response(200, json=PREDICATES_RESPONSE)

        client = _make_test_client(_make_transport(handler), max_retries=3)
        result = client.list()
        assert len(result.tables) == 2
        assert call_count == 2

    def test_retries_on_transport_error_then_succeeds(self):
        call_count = 0

        def handler(request: httpx.Request):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.ConnectError("Connection refused")
            return httpx.Response(200, json=PREDICATES_RESPONSE)

        client = _make_test_client(_make_transport(handler), max_retries=3)
        result = client.list()
        assert len(result.tables) == 2
        assert call_count == 2

    def test_retries_on_dns_error_then_succeeds(self):
        call_count = 0

        def handler(request: httpx.Request):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.ConnectError(
                    "[Errno -2] Name or service not known"
                )
            return httpx.Response(200, json=PREDICATES_RESPONSE)

        client = _make_test_client(_make_transport(handler), max_retries=3)
        result = client.list()
        assert len(result.tables) == 2
        assert call_count == 2

    def test_no_retry_on_timeout(self):
        call_count = 0

        def handler(request: httpx.Request):
            nonlocal call_count
            call_count += 1
            raise httpx.ReadTimeout("The read operation timed out")

        client = _make_test_client(_make_transport(handler), max_retries=3)
        with pytest.raises(httpx.ReadTimeout):
            client.list()
        assert call_count == 1

    def test_no_retry_on_400(self):
        call_count = 0

        def handler(request: httpx.Request):
            nonlocal call_count
            call_count += 1
            return _error_response(400, "bad_request", "Bad request")

        client = _make_test_client(_make_transport(handler), max_retries=3)
        with pytest.raises(ValidationError):
            client.list()
        assert call_count == 1

    def test_no_retry_on_401(self):
        call_count = 0

        def handler(request: httpx.Request):
            nonlocal call_count
            call_count += 1
            return _error_response(401, "unauthorized", "Invalid key")

        client = _make_test_client(_make_transport(handler), max_retries=3)
        with pytest.raises(AuthenticationError):
            client.list()
        assert call_count == 1

    def test_exhausts_retries_on_persistent_500(self):
        call_count = 0

        def handler(request: httpx.Request):
            nonlocal call_count
            call_count += 1
            return _error_response(500, "internal", "Server error")

        client = _make_test_client(_make_transport(handler), max_retries=3)
        with pytest.raises(SynalinksError) as exc_info:
            client.list()
        assert exc_info.value.status_code == 500
        assert call_count == 3

    def test_max_retries_1_disables_retry(self):
        call_count = 0

        def handler(request: httpx.Request):
            nonlocal call_count
            call_count += 1
            return _error_response(500, "internal", "Server error")

        client = _make_test_client(_make_transport(handler), max_retries=1)
        with pytest.raises(SynalinksError):
            client.list()
        assert call_count == 1

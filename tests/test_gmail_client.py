"""Tests for Gmail API retry behavior."""

import json
from unittest.mock import MagicMock, patch

import httplib2
import pytest
from googleapiclient.errors import HttpError

from gmail_invoice.gmail_extractor import (
    GMailClient,
    _backoff_seconds,
    _is_retryable_gmail_error,
)


def _http_error(status: int, reason: str | None = None) -> HttpError:
    body = {"error": {"code": status, "message": "error", "errors": []}}
    if reason:
        body["error"]["errors"].append({"reason": reason, "message": reason})
    content = json.dumps(body).encode()
    resp = httplib2.Response({"status": str(status), "content-type": "application/json"})
    return HttpError(resp, content)


def test_is_retryable_gmail_error_for_429():
    assert _is_retryable_gmail_error(_http_error(429)) is True


def test_is_retryable_gmail_error_for_rate_limit_403():
    assert _is_retryable_gmail_error(_http_error(403, "rateLimitExceeded")) is True
    assert _is_retryable_gmail_error(_http_error(403, "userRateLimitExceeded")) is True


def test_is_retryable_gmail_error_for_non_rate_limit_errors():
    assert _is_retryable_gmail_error(_http_error(403, "insufficientPermissions")) is False
    assert _is_retryable_gmail_error(_http_error(404)) is False


def test_backoff_seconds_stays_within_max():
    with patch("gmail_invoice.gmail_extractor.random.random", return_value=0.5):
        assert _backoff_seconds(0, max_backoff=64.0) == 1.5
        assert _backoff_seconds(10, max_backoff=64.0) == 64.0


@patch("gmail_invoice.gmail_extractor.time.sleep")
def test_execute_with_retry_recovers_from_rate_limit(mock_sleep):
    client = GMailClient.__new__(GMailClient)
    client._max_retries = 3
    client._max_backoff_s = 64.0

    request = MagicMock()
    request.execute.side_effect = [_http_error(429), {"messages": []}]

    result = client._execute_with_retry(request)

    assert result == {"messages": []}
    assert request.execute.call_count == 2
    mock_sleep.assert_called_once()


@patch("gmail_invoice.gmail_extractor.time.sleep")
def test_execute_with_retry_raises_non_retryable_error(mock_sleep):
    client = GMailClient.__new__(GMailClient)
    client._max_retries = 3
    client._max_backoff_s = 64.0

    request = MagicMock()
    request.execute.side_effect = _http_error(404)

    with pytest.raises(HttpError):
        client._execute_with_retry(request)

    assert request.execute.call_count == 1
    mock_sleep.assert_not_called()


@patch("gmail_invoice.gmail_extractor.time.sleep")
def test_execute_with_retry_exhausts_retries(mock_sleep):
    client = GMailClient.__new__(GMailClient)
    client._max_retries = 2
    client._max_backoff_s = 64.0

    request = MagicMock()
    request.execute.side_effect = [_http_error(429), _http_error(429), _http_error(429)]

    with pytest.raises(HttpError):
        client._execute_with_retry(request)

    assert request.execute.call_count == 3
    assert mock_sleep.call_count == 2

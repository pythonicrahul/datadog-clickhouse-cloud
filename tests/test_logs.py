"""Unit tests for the ClickHouse Cloud Datadog log check."""

import json
import time
from unittest.mock import MagicMock, patch, call

import pytest

# Mock the datadog_checks.base module before importing the check
import sys
from unittest.mock import MagicMock as _MagicMock

# Create a mock AgentCheck base class
mock_agent_check_module = _MagicMock()


class MockAgentCheck:
    OK = 0
    WARNING = 1
    CRITICAL = 2

    def __init__(self, name=None, init_config=None, instances=None):
        self._persistent_cache = {}
        self._sent_logs = []
        self._service_checks = []
        self._gauges = []
        self.log = _MagicMock()

    def read_persistent_cache(self, key):
        return self._persistent_cache.get(key)

    def write_persistent_cache(self, key, value):
        self._persistent_cache[key] = value

    def send_log(self, log_entry):
        self._sent_logs.append(log_entry)

    def service_check(self, name, status):
        self._service_checks.append((name, status))

    def gauge(self, name, value):
        self._gauges.append((name, value))


mock_agent_check_module.AgentCheck = MockAgentCheck
sys.modules["datadog_checks"] = _MagicMock()
sys.modules["datadog_checks.base"] = mock_agent_check_module

# Now import the check module
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "checks"))

from checks.clickhouse_cloud import ClickHouseCloudCheck


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_check(instance):
    """Create a ClickHouseCloudCheck instance with the mock base class."""
    check = ClickHouseCloudCheck("clickhouse_cloud", {}, [instance])
    return check


def _mock_query_response(rows):
    """Create a mock HTTP response returning JSONEachRow format."""
    response = MagicMock()
    response.status_code = 200
    response.text = "\n".join(json.dumps(r) for r in rows)
    response.raise_for_status = MagicMock()
    return response


# ---------------------------------------------------------------------------
# Query log payload tests
# ---------------------------------------------------------------------------


class TestBuildQueryLogPayload:
    def test_normal_query_is_info(self, default_instance, query_log_rows):
        check = _make_check(default_instance)
        row = query_log_rows[0]  # type=2, duration=120ms
        payload = check._build_query_log_payload(row)

        assert payload["status"] == "info"
        assert payload["clickhouse.query_type"] == "finish"
        assert payload["ddsource"] == "clickhouse_cloud"
        assert payload["service"] == "clickhouse"
        assert payload["clickhouse.query_id"] == "abc-123-def-456"
        assert payload["clickhouse.user"] == "default"
        assert payload["clickhouse.duration_ms"] == 120
        assert payload["message"] == row["query"]

    def test_slow_query_is_warning(self, default_instance, query_log_rows):
        check = _make_check(default_instance)
        row = query_log_rows[1]  # type=2, duration=8500ms > 5000ms threshold
        payload = check._build_query_log_payload(row)

        assert payload["status"] == "warning"
        assert payload["clickhouse.query_type"] == "finish"
        assert payload["clickhouse.duration_ms"] == 8500

    def test_exception_query_is_error(self, default_instance, query_log_rows):
        check = _make_check(default_instance)
        row = query_log_rows[2]  # type=3
        payload = check._build_query_log_payload(row)

        assert payload["status"] == "error"
        assert payload["clickhouse.query_type"] == "exception"
        assert payload["clickhouse.exception_code"] == 60
        assert "nonexistent" in payload["clickhouse.exception"]

    def test_tags_are_joined(self, default_instance, query_log_rows):
        check = _make_check(default_instance)
        row = query_log_rows[0]
        payload = check._build_query_log_payload(row)

        assert payload["ddtags"] == "env:test,clickhouse_cluster:test-cluster"

    def test_no_tags(self, default_instance, query_log_rows):
        default_instance["tags"] = []
        check = _make_check(default_instance)
        row = query_log_rows[0]
        payload = check._build_query_log_payload(row)

        assert payload["ddtags"] == ""


# ---------------------------------------------------------------------------
# Text log payload tests
# ---------------------------------------------------------------------------


class TestBuildTextLogPayload:
    def test_error_level(self, default_instance, text_log_rows):
        check = _make_check(default_instance)
        row = text_log_rows[0]  # Error
        payload = check._build_text_log_payload(row)

        assert payload["status"] == "error"
        assert payload["ddsource"] == "clickhouse_cloud"
        assert payload["clickhouse.logger"] == "MergeTreeBackgroundExecutor"
        assert "Memory limit exceeded" in payload["message"]

    def test_warning_level(self, default_instance, text_log_rows):
        check = _make_check(default_instance)
        row = text_log_rows[1]  # Warning
        payload = check._build_text_log_payload(row)

        assert payload["status"] == "warning"

    def test_fatal_level(self, default_instance, text_log_rows):
        check = _make_check(default_instance)
        row = text_log_rows[2]  # Fatal
        payload = check._build_text_log_payload(row)

        assert payload["status"] == "critical"
        assert payload["clickhouse.thread_id"] == "1"


# ---------------------------------------------------------------------------
# Cursor management tests
# ---------------------------------------------------------------------------


class TestCursorManagement:
    def test_get_cursor_returns_none_when_empty(self, default_instance):
        check = _make_check(default_instance)
        assert check._get_cursor("some_key") is None

    def test_set_and_get_cursor(self, default_instance):
        check = _make_check(default_instance)
        check._set_cursor("some_key", 1743246001000000)
        assert check._get_cursor("some_key") == 1743246001000000

    def test_default_cursor_is_reasonable(self, default_instance):
        check = _make_check(default_instance)
        cursor = check._default_cursor()
        now_us = int(time.time() * 1_000_000)
        backfill_us = 60 * 60 * 1_000_000  # 60 minutes

        # Should be within a few seconds of (now - 60 min)
        assert abs(cursor - (now_us - backfill_us)) < 5_000_000


# ---------------------------------------------------------------------------
# Full collection flow tests
# ---------------------------------------------------------------------------


class TestCollectQueryLogs:
    @patch("checks.clickhouse_cloud.ClickHouseCloudCheck._query_clickhouse")
    def test_sends_logs_and_updates_cursor(self, mock_query, default_instance, query_log_rows):
        check = _make_check(default_instance)
        mock_query.return_value = query_log_rows

        check._collect_query_logs()

        # Should send 3 log entries
        assert len(check._sent_logs) == 3

        # Cursor should be set to the last row's timestamp
        cursor = check._get_cursor("clickhouse_cloud.cursor.query_log")
        assert cursor == 1743246010000000

        # Service check should report OK
        assert ("clickhouse_cloud.query_log.can_connect", MockAgentCheck.OK) in check._service_checks

    @patch("checks.clickhouse_cloud.ClickHouseCloudCheck._query_clickhouse")
    def test_no_rows_does_not_update_cursor(self, mock_query, default_instance):
        check = _make_check(default_instance)
        mock_query.return_value = []

        check._collect_query_logs()

        assert len(check._sent_logs) == 0
        assert check._get_cursor("clickhouse_cloud.cursor.query_log") is None

    @patch("checks.clickhouse_cloud.ClickHouseCloudCheck._query_clickhouse")
    def test_query_failure_reports_critical(self, mock_query, default_instance):
        check = _make_check(default_instance)
        mock_query.side_effect = Exception("Connection refused")

        check._collect_query_logs()

        assert ("clickhouse_cloud.query_log.can_connect", MockAgentCheck.CRITICAL) in check._service_checks
        assert len(check._sent_logs) == 0


class TestCollectTextLogs:
    @patch("checks.clickhouse_cloud.ClickHouseCloudCheck._query_clickhouse")
    def test_sends_logs_and_updates_cursor(self, mock_query, default_instance, text_log_rows):
        check = _make_check(default_instance)
        mock_query.return_value = text_log_rows

        check._collect_text_logs()

        assert len(check._sent_logs) == 3

        cursor = check._get_cursor("clickhouse_cloud.cursor.text_log")
        assert cursor == 1743246070000000

    @patch("checks.clickhouse_cloud.ClickHouseCloudCheck._query_clickhouse")
    def test_query_failure_reports_critical(self, mock_query, default_instance):
        check = _make_check(default_instance)
        mock_query.side_effect = Exception("Timeout")

        check._collect_text_logs()

        assert ("clickhouse_cloud.text_log.can_connect", MockAgentCheck.CRITICAL) in check._service_checks


class TestCheckEntryPoint:
    @patch("checks.clickhouse_cloud.ClickHouseCloudCheck._query_clickhouse")
    def test_check_calls_both_collectors(self, mock_query, default_instance, query_log_rows, text_log_rows):
        check = _make_check(default_instance)
        # First call returns query logs, second returns text logs
        mock_query.side_effect = [query_log_rows, text_log_rows]

        check.check(default_instance)

        # All logs from both sources
        assert len(check._sent_logs) == 6

    @patch("checks.clickhouse_cloud.ClickHouseCloudCheck._query_clickhouse")
    def test_check_respects_disabled_collectors(self, mock_query, default_instance):
        default_instance["collect_query_logs"] = False
        default_instance["collect_text_logs"] = False
        check = _make_check(default_instance)

        check.check(default_instance)

        mock_query.assert_not_called()

    @patch("checks.clickhouse_cloud.ClickHouseCloudCheck._query_clickhouse")
    def test_cursor_persists_across_runs(self, mock_query, default_instance, query_log_rows):
        check = _make_check(default_instance)
        default_instance["collect_text_logs"] = False
        check.collect_text_logs = False

        # First run
        mock_query.return_value = query_log_rows
        check.check(default_instance)
        first_cursor = check._get_cursor("clickhouse_cloud.cursor.query_log")

        # Second run with no new data
        mock_query.return_value = []
        check.check(default_instance)
        second_cursor = check._get_cursor("clickhouse_cloud.cursor.query_log")

        # Cursor should not change on empty run
        assert first_cursor == second_cursor == 1743246010000000

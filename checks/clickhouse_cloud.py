"""
ClickHouse Cloud custom Datadog Agent check for log collection.

Collects query logs (system.query_log) and server logs (system.text_log)
from ClickHouse Cloud via the Cloud Query API and ships them to Datadog Logs.
"""

import json
import time

import requests
from datadog_checks.base import AgentCheck


QUERY_LOG_SQL = """
SELECT
    event_time,
    toUnixTimestamp64Micro(event_time_microseconds) AS cursor_us,
    query_id,
    user,
    query_duration_ms,
    memory_usage,
    read_rows,
    read_bytes,
    result_rows,
    written_rows,
    exception,
    exception_code,
    query,
    type,
    arrayStringConcat(tables, ', ') AS tables,
    client_name
FROM system.query_log
WHERE type IN ('QueryFinish', 'ExceptionWhileProcessing')
  AND event_time_microseconds > fromUnixTimestamp64Micro({last_cursor})
ORDER BY event_time_microseconds ASC
LIMIT {batch_size}
"""

TEXT_LOG_SQL = """
SELECT
    event_time,
    toUnixTimestamp64Micro(event_time_microseconds) AS cursor_us,
    level,
    logger_name,
    message,
    thread_id
FROM system.text_log
WHERE level IN ('Error', 'Warning', 'Fatal')
  AND event_time_microseconds > fromUnixTimestamp64Micro({last_cursor})
ORDER BY event_time_microseconds ASC
LIMIT {batch_size}
"""

CURSOR_QUERY_LOG = "clickhouse_cloud.cursor.query_log"
CURSOR_TEXT_LOG = "clickhouse_cloud.cursor.text_log"

# ClickHouse query_log type names (returned as strings by the Cloud Query API)
TYPE_QUERY_FINISH = "QueryFinish"
TYPE_QUERY_EXCEPTION = "ExceptionWhileProcessing"

# Datadog log level mappings
TEXT_LOG_LEVEL_MAP = {
    "Fatal": "critical",
    "Error": "error",
    "Warning": "warning",
}


class ClickHouseCloudCheck(AgentCheck):
    """Datadog Agent check that collects logs from ClickHouse Cloud system tables."""

    def __init__(self, name, init_config, instances):
        super().__init__(name, init_config, instances)

        instance = instances[0]
        self.service_id = instance["service_id"]
        self.key_id = instance["key_id"]
        self.key_secret = instance["key_secret"]

        self.collect_query_logs = instance.get("collect_query_logs", True)
        self.collect_text_logs = instance.get("collect_text_logs", True)
        self.batch_size = instance.get("log_batch_size", 1000)
        self.slow_query_threshold_ms = instance.get("slow_query_threshold_ms", 5000)
        self.initial_backfill_minutes = instance.get("initial_backfill_minutes", 60)
        self.custom_tags = instance.get("tags", [])

        self.base_url = "https://queries.clickhouse.cloud/service/{}/run".format(
            self.service_id
        )

        self._session = requests.Session()
        self._session.auth = (self.key_id, self.key_secret)
        self._session.headers.update({"Content-Type": "application/json"})
        self._session.verify = True

    # ------------------------------------------------------------------
    # Cursor management
    # ------------------------------------------------------------------

    def _get_cursor(self, key):
        """Retrieve the stored cursor (event_time_microseconds) from persistent cache."""
        cached = self.read_persistent_cache(key)
        if cached:
            return int(cached)
        return None

    def _set_cursor(self, key, value):
        """Persist the latest cursor value."""
        self.write_persistent_cache(key, str(value))

    def _default_cursor(self):
        """Return a microsecond timestamp for initial_backfill_minutes ago."""
        backfill_seconds = self.initial_backfill_minutes * 60
        # ClickHouse event_time_microseconds is a DateTime64(6) stored as UInt64 microseconds
        epoch_us = int((time.time() - backfill_seconds) * 1_000_000)
        return epoch_us

    def _timestamp_seconds(self, row):
        """Return a Unix timestamp in seconds for Datadog's send_log API."""
        try:
            return int(row.get("cursor_us", 0)) / 1_000_000
        except (TypeError, ValueError):
            return time.time()

    def _emit_log(self, log_entry):
        """Send log entry using Agent APIs available in the current runtime.

        Newer Datadog Agent runtimes expose AgentCheck.send_log(). Older runtimes
        do not; in that case we write JSON to the check logger as a fallback so
        the check keeps running without raising AttributeError.
        """
        send_log = getattr(self, "send_log", None)
        if callable(send_log):
            send_log(log_entry)
            return

        self.log.info(json.dumps(log_entry, separators=(",", ":")))

    # ------------------------------------------------------------------
    # ClickHouse HTTP interface
    # ------------------------------------------------------------------

    def _query_clickhouse(self, sql):
        """Execute a SQL query against ClickHouse Cloud via the Cloud Query API.

        Returns a list of dicts (one per row) using JSONEachRow format.
        """
        params = {"format": "JSONEachRow"}
        body = {"sql": sql}

        try:
            resp = self._session.post(
                self.base_url, params=params, json=body, timeout=30
            )
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            self.log.error("ClickHouse Cloud API query failed: %s", e)
            raise

        rows = []
        for line in resp.text.strip().splitlines():
            if line:
                rows.append(json.loads(line))
        return rows

    # ------------------------------------------------------------------
    # Query log collection
    # ------------------------------------------------------------------

    def _collect_query_logs(self):
        """Fetch new rows from system.query_log and send as Datadog logs."""
        cursor = self._get_cursor(CURSOR_QUERY_LOG)
        if cursor is None:
            cursor = self._default_cursor()

        sql = QUERY_LOG_SQL.format(last_cursor=cursor, batch_size=self.batch_size)

        try:
            rows = self._query_clickhouse(sql)
        except Exception:
            self.service_check("clickhouse_cloud.query_log.can_connect", AgentCheck.CRITICAL)
            return

        self.service_check("clickhouse_cloud.query_log.can_connect", AgentCheck.OK)
        self.gauge("clickhouse_cloud.query_log.rows_collected", len(rows))
        self.log.debug("query_log: fetched %d rows", len(rows))

        if not rows:
            return

        for row in rows:
            log_entry = self._build_query_log_payload(row)
            self._emit_log(log_entry)

        # Update cursor to the last row's microsecond timestamp
        last_cursor = int(rows[-1]["cursor_us"])
        self._set_cursor(CURSOR_QUERY_LOG, last_cursor)

    def _build_query_log_payload(self, row):
        """Map a query_log row to a Datadog log entry."""
        query_type = row.get("type", "")

        # Determine log level
        if query_type == TYPE_QUERY_EXCEPTION:
            level = "error"
            type_label = "exception"
        else:
            duration_ms = int(row.get("query_duration_ms", 0))
            if duration_ms >= self.slow_query_threshold_ms:
                level = "warning"
            else:
                level = "info"
            type_label = "finish"

        return {
            "timestamp": self._timestamp_seconds(row),
            "message": row.get("query", ""),
            "ddsource": "clickhouse_cloud",
            "ddtags": ",".join(self.custom_tags) if self.custom_tags else "",
            "service": "clickhouse",
            "status": level,
            "clickhouse.query_id": row.get("query_id", ""),
            "clickhouse.user": row.get("user", ""),
            "clickhouse.duration_ms": int(row.get("query_duration_ms", 0)),
            "clickhouse.memory_bytes": int(row.get("memory_usage", 0)),
            "clickhouse.read_rows": int(row.get("read_rows", 0)),
            "clickhouse.read_bytes": int(row.get("read_bytes", 0)),
            "clickhouse.result_rows": int(row.get("result_rows", 0)),
            "clickhouse.written_rows": int(row.get("written_rows", 0)),
            "clickhouse.exception": row.get("exception", ""),
            "clickhouse.exception_code": int(row.get("exception_code", 0)),
            "clickhouse.query_type": type_label,
            "clickhouse.tables": row.get("tables", ""),
            "clickhouse.client": row.get("client_name", ""),
        }

    # ------------------------------------------------------------------
    # Text log collection
    # ------------------------------------------------------------------

    def _collect_text_logs(self):
        """Fetch new rows from system.text_log and send as Datadog logs."""
        cursor = self._get_cursor(CURSOR_TEXT_LOG)
        if cursor is None:
            cursor = self._default_cursor()

        sql = TEXT_LOG_SQL.format(last_cursor=cursor, batch_size=self.batch_size)

        try:
            rows = self._query_clickhouse(sql)
        except Exception:
            self.service_check("clickhouse_cloud.text_log.can_connect", AgentCheck.CRITICAL)
            return

        self.service_check("clickhouse_cloud.text_log.can_connect", AgentCheck.OK)
        self.gauge("clickhouse_cloud.text_log.rows_collected", len(rows))
        self.log.debug("text_log: fetched %d rows", len(rows))

        if not rows:
            return

        for row in rows:
            log_entry = self._build_text_log_payload(row)
            self._emit_log(log_entry)

        last_cursor = int(rows[-1]["cursor_us"])
        self._set_cursor(CURSOR_TEXT_LOG, last_cursor)

    def _build_text_log_payload(self, row):
        """Map a text_log row to a Datadog log entry."""
        level = TEXT_LOG_LEVEL_MAP.get(row.get("level", ""), "warning")

        return {
            "timestamp": self._timestamp_seconds(row),
            "message": row.get("message", ""),
            "ddsource": "clickhouse_cloud",
            "ddtags": ",".join(self.custom_tags) if self.custom_tags else "",
            "service": "clickhouse",
            "status": level,
            "clickhouse.logger": row.get("logger_name", ""),
            "clickhouse.thread_id": str(row.get("thread_id", "")),
        }

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def check(self, instance):
        """Main check method called by the Datadog Agent on each run."""
        if self.collect_query_logs:
            self._collect_query_logs()

        if self.collect_text_logs:
            self._collect_text_logs()

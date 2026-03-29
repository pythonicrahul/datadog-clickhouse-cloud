"""SQL query constants for ClickHouse Cloud log collection."""

QUERY_LOG_SQL = """
SELECT
    event_time,
    event_time_microseconds,
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
WHERE type IN (2, 3)
  AND event_time_microseconds > {last_cursor}
ORDER BY event_time_microseconds ASC
LIMIT {batch_size}
"""

TEXT_LOG_SQL = """
SELECT
    event_time,
    event_time_microseconds,
    level,
    logger_name,
    message,
    thread_id
FROM system.text_log
WHERE level IN ('Error', 'Warning', 'Fatal')
  AND event_time_microseconds > {last_cursor}
ORDER BY event_time_microseconds ASC
LIMIT {batch_size}
"""

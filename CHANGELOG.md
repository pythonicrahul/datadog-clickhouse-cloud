# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-04-03

### Added
- Custom Datadog Agent check for ClickHouse Cloud log collection
- Query log collection from `system.query_log` (completed queries and exceptions)
- Text log collection from `system.text_log` (Error, Warning, Fatal levels)
- OpenMetrics configuration for ClickHouse Cloud Prometheus endpoint
- Cursor-based pagination with duplicate-delivery-over-loss semantics
- Configurable batch size, slow-query threshold, backfill window, and query timeout
- Input validation with bounds checking on all numeric config parameters
- HTTP retry logic (2 retries with backoff on 502/503/504)
- Configurable `cluster_name` for the Datadog `service` field
- `ddsource: clickhouse` on all log entries for Datadog pipeline compatibility
- Comprehensive test suite (53 tests)
- CI workflow with ruff lint and pytest across Python 3.10/3.11/3.12
- Dependabot configuration for pip and GitHub Actions

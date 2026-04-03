"""Shared test fixtures for ClickHouse Cloud Datadog check tests."""

import json
import os
import pytest


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture
def query_log_rows():
    with open(os.path.join(FIXTURES_DIR, "query_log_rows.json")) as f:
        return json.load(f)


@pytest.fixture
def text_log_rows():
    with open(os.path.join(FIXTURES_DIR, "text_log_rows.json")) as f:
        return json.load(f)


@pytest.fixture
def default_instance():
    return {
        "service_id": "test-service-uuid",
        "key_id": "test-key-id",
        "key_secret": "test-key-secret",
        "collect_query_logs": True,
        "collect_text_logs": True,
        "log_batch_size": 1000,
        "slow_query_threshold_ms": 5000,
        "initial_backfill_minutes": 60,
        "tags": ["env:test", "clickhouse_cluster:test-cluster"],
    }

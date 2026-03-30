# ClickHouse Cloud + Datadog — Complete Observability

Full metrics and log collection from ClickHouse Cloud into Datadog. No extra dependencies — just config files and one Python check.

| Component | Mechanism | What it does |
|-----------|-----------|-------------|
| **Metrics** | Datadog OpenMetrics check (config only) | Scrapes all key ClickHouse server metrics via the Prometheus `/metrics` endpoint |
| **Logs** | Custom Python Agent check | Ships query logs + server error/warning logs from `system.query_log` and `system.text_log` |

---

## What You Get

**Metrics:** Active queries, connections, memory, merges, disk usage, throughput — all shipped as `clickhouse.*` metrics in Datadog.

**Logs:** Every completed/failed query with duration, memory, rows scanned, and exception details. Plus server-level errors, warnings, and fatal messages.

Query logs are tagged with severity:
- `info` — normal queries
- `warning` — slow queries (configurable threshold, default 5s)
- `error` — failed queries with exception details

---

## Prerequisites

- **Datadog account** with an API key
- **ClickHouse Cloud cluster** with an API key (Settings → API Keys in the Cloud console)
- **Linux VM** with the Datadog Agent installed ([install guide](https://docs.datadoghq.com/agent/basic_agent_usage/))

---

## Step 1 — Install the Datadog Agent

If not already installed:

```bash
DD_API_KEY=<your-dd-api-key> DD_SITE="datadoghq.com" bash -c "$(curl -L https://install.datadoghq.com/scripts/install_script_agent7.sh)"
```

Verify it's running:

```bash
sudo systemctl status datadog-agent
```

---

## Step 2 — Enable Logs Collection

Edit the main Datadog Agent config to enable log collection:

```bash
sudo sed -i 's/# logs_enabled: false/logs_enabled: true/' /etc/datadog-agent/datadog.yaml
```

Or manually set `logs_enabled: true` in `/etc/datadog-agent/datadog.yaml`.

---

## Step 3 — Configure Metrics (OpenMetrics Check)

Copy the example config:

```bash
sudo cp conf.d/openmetrics_clickhouse.yaml.example \
  /etc/datadog-agent/conf.d/openmetrics.d/conf.yaml
```

Edit it with your ClickHouse Cloud details:

```bash
sudo nano /etc/datadog-agent/conf.d/openmetrics.d/conf.yaml
```

Replace the placeholders:
- `<your-cluster>` → your ClickHouse Cloud hostname (e.g., `abc123.us-east-1.aws`)
- `<your-user>` → your ClickHouse user (usually `default`)
- `<your-api-key>` → your ClickHouse Cloud API key
- `<your-cluster-name>` → a friendly name for tagging

**Full config reference:** [conf.d/openmetrics_clickhouse.yaml.example](conf.d/openmetrics_clickhouse.yaml.example)

### Metrics Collected

| Category | Metrics |
|----------|---------|
| Queries & Connections | `ClickHouseMetrics_Query`, `ClickHouseMetrics_TCPConnection`, `ClickHouseMetrics_HTTPConnection`, `ClickHouseProfileEvents_Query`, `ClickHouseProfileEvents_SelectQuery`, `ClickHouseProfileEvents_InsertQuery`, `ClickHouseProfileEvents_FailedQuery` |
| Memory | `ClickHouseAsyncMetrics_MemoryResident`, `ClickHouseAsyncMetrics_MarkCacheBytes`, `ClickHouseAsyncMetrics_UncompressedCacheBytes` |
| Merges & Storage | `ClickHouseMetrics_Merge`, `ClickHouseMetrics_PartMutation`, `ClickHouseAsyncMetrics_DiskUsed_default`, `ClickHouseAsyncMetrics_DiskAvailable_default` |
| Throughput | `ClickHouseProfileEvents_InsertedRows`, `ClickHouseProfileEvents_ReadCompressedBytes`, `ClickHouseProfileEvents_NetworkReceiveBytes`, `ClickHouseProfileEvents_NetworkSendBytes` |

---

## Step 4 — Install the Log Check

Copy the custom check:

```bash
sudo cp checks/clickhouse_cloud.py /etc/datadog-agent/checks.d/clickhouse_cloud.py
```

---

## Step 5 — Configure the Log Check

Create the config directory and copy the example:

```bash
sudo mkdir -p /etc/datadog-agent/conf.d/clickhouse_cloud.d
sudo cp conf.d/clickhouse_cloud.yaml.example \
  /etc/datadog-agent/conf.d/clickhouse_cloud.d/conf.yaml
```

Edit it with your ClickHouse Cloud details:

```bash
sudo nano /etc/datadog-agent/conf.d/clickhouse_cloud.d/conf.yaml
```

Replace the placeholders:
- `<your-cluster>` → your ClickHouse Cloud hostname
- `<your-user>` → your ClickHouse user
- `<your-api-key>` → your ClickHouse Cloud API key

**Configuration options:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `host` | *(required)* | ClickHouse Cloud hostname |
| `port` | `8443` | HTTPS port |
| `user` | *(required)* | ClickHouse username |
| `api_key` | *(required)* | ClickHouse Cloud API key |
| `collect_query_logs` | `true` | Enable query log collection |
| `collect_text_logs` | `true` | Enable server log collection |
| `log_batch_size` | `1000` | Max rows fetched per check run |
| `slow_query_threshold_ms` | `5000` | Queries slower than this are tagged `warning` |
| `initial_backfill_minutes` | `60` | How far back to look on first run |

---

## Step 6 — Restart Agent & Verify

```bash
sudo systemctl restart datadog-agent
```

Check agent status:

```bash
sudo datadog-agent status
```

Look for `clickhouse_cloud` in the Checks section and `openmetrics` with your ClickHouse endpoint.

Dry-run the log check:

```bash
sudo datadog-agent check clickhouse_cloud
```

You should see output showing rows collected from `query_log` and `text_log`.

---

## Troubleshooting

### Agent not picking up the check

Verify files are in the right locations:

```bash
ls -la /etc/datadog-agent/checks.d/clickhouse_cloud.py
ls -la /etc/datadog-agent/checks.d/queries.py
ls -la /etc/datadog-agent/conf.d/clickhouse_cloud.d/conf.yaml
```

Check agent logs:

```bash
sudo tail -50 /var/log/datadog/agent.log | grep -i clickhouse
```

### SSL / TLS errors

ClickHouse Cloud requires HTTPS. Make sure your VM's CA certificates are up to date:

```bash
sudo apt-get update && sudo apt-get install -y ca-certificates  # Debian/Ubuntu
sudo yum update ca-certificates                                   # RHEL/CentOS
```

### No logs appearing in Datadog

1. Confirm `logs_enabled: true` in `/etc/datadog-agent/datadog.yaml`
2. Run `sudo datadog-agent check clickhouse_cloud` — the output shows how many rows were fetched
3. Check that your ClickHouse user has access to `system.query_log` and `system.text_log`

### Duplicate logs

The check uses persistent cursors based on `event_time_microseconds`. Duplicates should not occur under normal operation. If you see them:

1. Stop the agent: `sudo systemctl stop datadog-agent`
2. Clear the cache: `sudo rm /opt/datadog-agent/run/clickhouse_cloud*`
3. Restart: `sudo systemctl start datadog-agent`

---

## Architecture

```
ClickHouse Cloud
  └── HTTPS Interface (:8443)
        ├── /metrics endpoint  ──────────► OpenMetrics Check (built-in DD Agent)
        │                                        │
        ├── system.query_log   ──┐               ▼
        └── system.text_log   ──┴──► Custom Python Check
                                           │
                                    Datadog Agent
                                     ├── Metrics API
                                     └── Logs API
```

**Auth:** ClickHouse Cloud API keys via `X-ClickHouse-User` and `X-ClickHouse-Key` headers.

**Transport:** HTTPS only (port 8443). No extra dependencies — uses the `requests` library already bundled with the Datadog Agent.

**State:** Persistent cursors (`event_time_microseconds`) survive agent restarts. Cursor is only updated after successful log submission — guarantees at-least-once delivery.

---

## Local Development

Run unit tests:

```bash
pip install pytest requests
pytest tests/ -v
```

---

## Contributing

1. Fork the repo
2. Create a feature branch
3. Make your changes with tests
4. Open a PR

---

## License

See [LICENSE](LICENSE).

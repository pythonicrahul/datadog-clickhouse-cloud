# ClickHouse Cloud + Datadog

This repo adds ClickHouse Cloud observability to a server where Datadog Agent is already installed.

- Metrics: OpenMetrics config using ClickHouse Cloud Prometheus API
- Logs: custom check reading system.query_log and system.text_log from ClickHouse Cloud Query API

## Files You Need

- Check code: [checks/clickhouse_cloud.py](checks/clickhouse_cloud.py)
- Logs config template: [conf.d/clickhouse_cloud.d/conf.yaml.example](conf.d/clickhouse_cloud.d/conf.yaml.example)
- Metrics config template: [conf.d/openmetrics.d/conf.yaml.example](conf.d/openmetrics.d/conf.yaml.example)

## Best-Practice Server Setup

1. Copy check and config templates

```bash
sudo cp checks/clickhouse_cloud.py /etc/datadog-agent/checks.d/clickhouse_cloud.py

sudo mkdir -p /etc/datadog-agent/conf.d/clickhouse_cloud.d
sudo cp conf.d/clickhouse_cloud.d/conf.yaml.example /etc/datadog-agent/conf.d/clickhouse_cloud.d/conf.yaml

sudo mkdir -p /etc/datadog-agent/conf.d/openmetrics.d
sudo cp conf.d/openmetrics.d/conf.yaml.example /etc/datadog-agent/conf.d/openmetrics.d/conf.yaml
```

2. Set required file permissions

```bash
sudo chown dd-agent:dd-agent /etc/datadog-agent/checks.d/clickhouse_cloud.py
sudo chown dd-agent:dd-agent /etc/datadog-agent/conf.d/clickhouse_cloud.d/conf.yaml
sudo chown dd-agent:dd-agent /etc/datadog-agent/conf.d/openmetrics.d/conf.yaml

sudo chmod 644 /etc/datadog-agent/checks.d/clickhouse_cloud.py
sudo chmod 640 /etc/datadog-agent/conf.d/clickhouse_cloud.d/conf.yaml
sudo chmod 640 /etc/datadog-agent/conf.d/openmetrics.d/conf.yaml
```

3. Edit config values

- In /etc/datadog-agent/conf.d/clickhouse_cloud.d/conf.yaml set:
  - service_id
  - key_id
  - key_secret
- In /etc/datadog-agent/conf.d/openmetrics.d/conf.yaml set:
  - openmetrics_endpoint with your organization/service IDs
  - username (key_id)
  - password (key_secret)
  - metrics: default template sends all ClickHouse metrics (`"^ClickHouse.*"`)
  - optional: replace with a limited allowlist if you want lower metric volume

4. Enable Datadog logs and restart agent

```bash
sudo sed -i 's/# logs_enabled: false/logs_enabled: true/' /etc/datadog-agent/datadog.yaml
sudo systemctl restart datadog-agent
```

5. Verify checks

```bash
sudo datadog-agent check clickhouse_cloud
sudo datadog-agent status
```

## Quick Troubleshooting

- No logs/metrics:
  - confirm API key permissions and Service Query Endpoint
  - check: sudo datadog-agent check clickhouse_cloud
  - check: sudo datadog-agent status
- Reset cursors if needed:

```bash
sudo systemctl stop datadog-agent
sudo rm -f /opt/datadog-agent/run/clickhouse_cloud*
sudo systemctl start datadog-agent
```

## License

See [LICENSE](LICENSE).

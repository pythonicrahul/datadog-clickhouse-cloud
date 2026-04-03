FROM datadog/agent:latest

COPY checks/clickhouse_cloud.py /etc/datadog-agent/checks.d/clickhouse_cloud.py
COPY conf.d/clickhouse_cloud.d/conf.yaml /etc/datadog-agent/conf.d/clickhouse_cloud.d/conf.yaml
COPY conf.d/openmetrics.d/conf.yaml /etc/datadog-agent/conf.d/openmetrics.d/conf.yaml

ENV DD_SITE=us5.datadoghq.com \
    DD_HOSTNAME=clickhouse-cloud-monitor \
    DD_LOGS_ENABLED=true \
    DD_LOGS_CONFIG_CONTAINER_COLLECT_ALL=true \
    DD_PROCESS_AGENT_ENABLED=true \
    DD_SKIP_SSL_VALIDATION=true

RUN chmod 644 /etc/datadog-agent/checks.d/clickhouse_cloud.py
RUN chmod 644 /etc/datadog-agent/conf.d/clickhouse_cloud.d/conf.yaml
RUN chmod 644 /etc/datadog-agent/conf.d/openmetrics.d/conf.yaml
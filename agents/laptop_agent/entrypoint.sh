#!/bin/bash
set -e

# NODE_EXPORTER_URL defaults to localhost:9100 (internal node_exporter)
# On macOS set -e NODE_EXPORTER_URL=host.docker.internal:9100 and install
# node_exporter via brew separately — internal one only sees the Docker VM.
NODE_EXPORTER_URL="${NODE_EXPORTER_URL:-localhost:9100}"
INSTANCE_NAME="${INSTANCE_NAME:-my-laptop}"

echo "[laptop-agent] Starting for client: ${CLIENT_SLUG}"

# Start internal Node Exporter only when targeting localhost
if [ "$NODE_EXPORTER_URL" = "localhost:9100" ]; then
    echo "[laptop-agent] Starting Node Exporter..."
    /bin/node_exporter --web.listen-address=:9100 &
    sleep 1
fi

# Generate Prometheus agent config
cat > /tmp/prometheus.yml <<EOF
global:
  scrape_interval: 15s
  external_labels:
    client: "${CLIENT_SLUG}"

scrape_configs:
  - job_name: laptop
    static_configs:
      - targets: ["${NODE_EXPORTER_URL}"]
        labels:
          instance: "${INSTANCE_NAME}"
          job: "laptop"

remote_write:
  - url: "${PLATFORM_URL}/remote_write"
    bearer_token: "${CLIENT_TOKEN}"
    queue_config:
      max_samples_per_send: 1000
      batch_send_deadline: 5s
EOF

echo "[laptop-agent] Prometheus agent connecting to ${PLATFORM_URL}/remote_write"
mkdir -p /tmp/agent-data

exec /bin/prometheus \
    --config.file=/tmp/prometheus.yml \
    --enable-feature=agent \
    --storage.agent.path=/tmp/agent-data \
    --web.listen-address=:9091

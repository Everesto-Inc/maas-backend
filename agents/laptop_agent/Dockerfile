FROM ubuntu:22.04

RUN apt-get update && apt-get install -y wget curl && rm -rf /var/lib/apt/lists/*

# Copy binaries from official images — no extra deps needed
COPY --from=prom/node-exporter:latest  /bin/node_exporter /bin/node_exporter
COPY --from=prom/prometheus:latest     /bin/prometheus    /bin/prometheus

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]

FROM ubuntu:22.04

RUN apt-get update && apt-get install -y wget curl && rm -rf /var/lib/apt/lists/*

# Copy binaries from official images — pinned to versions with fixed Go stdlib
COPY --from=prom/node-exporter:v1.9.1  /bin/node_exporter /bin/node_exporter
COPY --from=prom/prometheus:v3.4.1     /bin/prometheus    /bin/prometheus

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]

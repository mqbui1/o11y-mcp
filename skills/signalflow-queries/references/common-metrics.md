# Common Splunk Observability Metric Names

## APM Metrics (OpenTelemetry / Splunk APM)

| Metric | Unit | Description |
|---|---|---|
| `service.request.duration.ns.p50` | nanoseconds | Median request latency |
| `service.request.duration.ns.p90` | nanoseconds | P90 request latency |
| `service.request.duration.ns.p99` | nanoseconds | P99 request latency |
| `spans.count` | count | Total spans (requests) |

Key APM dimensions:
- `sf_service` — service name
- `sf_operation` — operation/endpoint name
- `sf_environment` — APM environment
- `sf_httpMethod` — HTTP method (GET, POST, etc.)
- `error` — "true" or "false"
- `http.status_code` — response status code

Note: `service.request.duration.ns.*` values are nanoseconds.
- 1ms = 1,000,000 ns
- 100ms = 100,000,000 ns
- 1s = 1,000,000,000 ns

---

## Infrastructure Metrics (Splunk OTel Collector / collectd)

### CPU
| Metric | Unit | Description |
|---|---|---|
| `cpu.utilization` | percent (0-100) | CPU utilization percentage |
| `cpu.idle` | percent | CPU idle percentage |
| `cpu.user` | percent | User-space CPU usage |
| `cpu.sys` | percent | Kernel CPU usage |

### Memory
| Metric | Unit | Description |
|---|---|---|
| `memory.utilization` | percent (0-100) | Memory utilization percentage |
| `memory.used` | bytes | Used memory |
| `memory.free` | bytes | Free memory |
| `memory.total` | bytes | Total memory |

### Disk
| Metric | Unit | Description |
|---|---|---|
| `disk.utilization` | percent (0-100) | Disk usage percentage |
| `disk.total` | bytes | Total disk space |
| `disk.free` | bytes | Free disk space |
| `disk_ops.read` | ops/s | Disk read operations |
| `disk_ops.write` | ops/s | Disk write operations |

### Network
| Metric | Unit | Description |
|---|---|---|
| `network.total` | bytes/s | Total network throughput |
| `network.rx_bytes` | bytes/s | Receive throughput |
| `network.tx_bytes` | bytes/s | Transmit throughput |
| `network.rx_errors` | count/s | Receive errors |
| `network.tx_errors` | count/s | Transmit errors |

Key host dimensions:
- `host` — hostname
- `plugin` — collectd plugin name
- `plugin_instance` — e.g., disk device name

---

## Kubernetes Metrics (Splunk OTel Collector — k8s receiver)

| Metric | Unit | Description |
|---|---|---|
| `k8s.pod.cpu.utilization` | cores | Pod CPU usage |
| `k8s.pod.memory.usage` | bytes | Pod memory usage |
| `k8s.pod.network.rx_bytes` | bytes | Pod network receive |
| `k8s.pod.network.tx_bytes` | bytes | Pod network transmit |
| `k8s.node.cpu.utilization` | cores | Node CPU usage |
| `k8s.node.memory.usage` | bytes | Node memory usage |
| `k8s.deployment.desired` | count | Desired replicas |
| `k8s.deployment.available` | count | Available replicas |
| `container_cpu_utilization` | percent | Container CPU % |
| `container_memory_usage_bytes` | bytes | Container memory |

Key Kubernetes dimensions:
- `kubernetes_pod_name` — pod name
- `kubernetes_namespace` — namespace
- `kubernetes_cluster` — cluster name
- `kubernetes_node` — node name
- `container_image` — container image

---

## JVM Metrics (Java / OpenTelemetry)

| Metric | Unit | Description |
|---|---|---|
| `jvm.memory.used` | bytes | JVM heap used |
| `jvm.memory.committed` | bytes | JVM heap committed |
| `jvm.gc.duration` | ms | GC pause duration |
| `jvm.gc.count` | count | GC event count |
| `jvm.threads.count` | count | Active threads |
| `process.cpu.time` | ns | CPU time consumed |

---

## MySQL / Database (collectd)

| Metric | Unit | Description |
|---|---|---|
| `mysql_commands.select` | ops/s | SELECT rate |
| `mysql_commands.insert` | ops/s | INSERT rate |
| `mysql_commands.update` | ops/s | UPDATE rate |
| `mysql_commands.delete` | ops/s | DELETE rate |
| `mysql_threads.connected` | count | Active connections |
| `mysql_octets.rx` | bytes/s | Bytes received |
| `mysql_octets.tx` | bytes/s | Bytes sent |

---

## HTTP / Web Server (NGINX, Apache)

| Metric | Unit | Description |
|---|---|---|
| `nginx_connections.active` | count | Active connections |
| `nginx_requests` | requests/s | Request rate |
| `apache_connections` | count | Active connections |
| `apache_requests` | requests/s | Request rate |

---

## Tips for Finding Metrics

1. Use `search_metrics` with partial names: `query='cpu*'` or `query='*.p99'`
2. Use `search_metric_time_series` to find metrics with specific dimension combinations:
   `query='sf_metric:spans.count AND sf_service:api-gateway'`
3. If a metric name is unknown, start broad with `search_metrics` query='*' and filter results

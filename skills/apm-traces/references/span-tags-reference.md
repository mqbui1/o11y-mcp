# Span Tags Reference

## Standard OpenTelemetry Span Tags

### HTTP Client/Server Spans
| Tag | Example Values | Description |
|---|---|---|
| `http.method` | GET, POST, PUT, DELETE | HTTP method |
| `http.url` | `https://api.example.com/v1/users` | Full request URL |
| `http.target` | `/v1/users?page=1` | Request path + query string |
| `http.host` | `api.example.com` | Target host |
| `http.scheme` | http, https | Protocol |
| `http.status_code` | 200, 404, 500 | Response status code |
| `http.flavor` | 1.1, 2.0, h2 | HTTP version |
| `http.user_agent` | Mozilla/5.0... | Client user agent |
| `http.request_content_length` | 1024 | Request body size in bytes |
| `http.response_content_length` | 512 | Response body size in bytes |
| `http.route` | /owners/{ownerId} | Parameterized route template |

### Database Spans
| Tag | Example Values | Description |
|---|---|---|
| `db.system` | mysql, postgresql, redis, mongodb | DB type |
| `db.instance` | petclinic, mydb | Database name |
| `db.statement` | SELECT * FROM owners WHERE id=? | Query text (may be truncated) |
| `db.operation` | SELECT, INSERT, UPDATE, DELETE | SQL operation type |
| `db.user` | root, app_user | Database user |
| `db.connection_string` | mysql://localhost:3306/db | Connection string |
| `db.rows_affected` | 1, 42 | Rows affected (some drivers) |

### gRPC Spans
| Tag | Example Values | Description |
|---|---|---|
| `rpc.system` | grpc | RPC framework |
| `rpc.service` | helloworld.Greeter | Service name |
| `rpc.method` | SayHello | Method name |
| `rpc.grpc.status_code` | 0 (OK), 14 (UNAVAILABLE) | gRPC status code |

### Messaging Spans (Kafka, RabbitMQ, etc.)
| Tag | Example Values | Description |
|---|---|---|
| `messaging.system` | kafka, rabbitmq, activemq | Messaging system |
| `messaging.destination` | my-topic, my-queue | Topic or queue name |
| `messaging.operation` | send, receive, process | Operation type |
| `messaging.message_id` | abc-123 | Message identifier |

### Span Kind
| `span.kind` | Meaning |
|---|---|
| `server` | Received a request (inbound) |
| `client` | Made a request (outbound) |
| `producer` | Sent a message |
| `consumer` | Received a message |
| `internal` | Internal operation, no I/O |

---

## Splunk APM Dimensions

These dimensions are added by the Splunk APM agent/collector:

| Dimension | Example | Description |
|---|---|---|
| `sf_service` | api-gateway | Service name (OTEL_SERVICE_NAME) |
| `sf_operation` | GET /owners/{ownerId} | Span operation name |
| `sf_environment` | production | APM environment |
| `sf_httpMethod` | GET | HTTP method (APM dimension) |

---

## Error Tags
| Tag | Values | Description |
|---|---|---|
| `error` | true, false | Whether span is an error |
| `error.message` | NullPointerException... | Error message text |
| `error.type` | java.lang.NPE | Exception class |
| `error.stack` | at com.example... | Stack trace (may be truncated) |
| `otel.status_code` | OK, ERROR | OpenTelemetry status |
| `otel.status_description` | Connection refused | Status description |

---

## Deployment / Version Tags
| Tag | Example | Description |
|---|---|---|
| `deployment.environment` | production | Deployment environment |
| `deployment.version` | v2.3.1 | Application version |
| `service.version` | 1.0.0 | Service version |
| `service.namespace` | platform | Service namespace/team |

---

## Resource Attributes (added by OTel SDK/collector)
| Tag | Example | Description |
|---|---|---|
| `host.name` | web-server-01 | Hostname |
| `host.ip` | 10.0.1.5 | Host IP |
| `os.type` | linux | Operating system |
| `process.pid` | 12345 | Process ID |
| `process.runtime.name` | OpenJDK Runtime | Runtime name |
| `process.runtime.version` | 11.0.15 | Runtime version |
| `container.id` | a1b2c3d4 | Container ID |
| `k8s.pod.name` | api-gateway-7d4f | Kubernetes pod name |
| `k8s.namespace.name` | production | Kubernetes namespace |
| `k8s.cluster.name` | my-cluster | Kubernetes cluster |
| `k8s.node.name` | ip-10-0-1-5 | Kubernetes node |

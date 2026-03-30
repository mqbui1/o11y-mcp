---
name: apm-traces
description: >
  How to search, retrieve, and analyze distributed traces in Splunk APM —
  finding traces by service/operation/tags, reading span waterfalls, interpreting
  latency contributors, and navigating the service map. Use this skill for
  deep trace investigation, understanding service dependencies, or exploring
  APM data.
  Trigger phrases: "show me traces", "find slow traces", "get a trace",
  "analyze this trace", "what operations are slow", "show me the service map",
  "service dependencies", "trace analysis", "find error traces",
  "search traces for service", "what services call my service",
  "trace waterfall", "span analysis", "APM investigation",
  or any request to search, retrieve, or analyze APM traces or service maps.
metadata:
  version: "1.0.0"
allowed-tools:
  - mcp__splunk-observability__search_traces
  - mcp__splunk-observability__get_trace
  - mcp__splunk-observability__get_trace_full
  - mcp__splunk-observability__get_trace_analysis
  - mcp__splunk-observability__get_trace_outliers
  - mcp__splunk-observability__get_service_map_for_trace
  - mcp__splunk-observability__get_service_topology
  - mcp__splunk-observability__get_service_dependencies
  - mcp__splunk-observability__search_service_map
  - mcp__splunk-observability__list_trace_services
  - mcp__splunk-observability__search_trace_span_tags
  - mcp__splunk-observability__execute_signalflow
  - AskUserQuestion
---

# Splunk APM Traces

Complete reference for working with distributed traces in Splunk APM.

---

## Tool Selection Guide

| Goal | Best tool |
|---|---|
| Find traces matching criteria | `search_traces` |
| Ranked top latency contributors | `get_trace_analysis` |
| All spans + tags for one trace | `get_trace_full` |
| Raw span snapshot | `get_trace` |
| Find worst-latency operations (no trace ID needed) | `get_trace_outliers` |
| See which services a trace touched | `get_service_map_for_trace` |
| Full environment service map | `get_service_topology` |
| Direct dependencies of one service | `get_service_dependencies` |
| Available span tag keys/values | `search_trace_span_tags` |
| All services with recent traces | `list_trace_services` |

---

## Workflow: Find and Analyze a Trace

### When you know the service but not the trace ID

1. `search_traces` — filter by `environment`, `services`, and any known tags
2. Pick a representative trace ID from results
3. `get_trace_analysis` — get ranked latency contributors (fastest path to root cause)
4. `get_trace_full` — inspect specific spans and their tags

### When you have a trace ID already

1. `get_trace_analysis` — start here for latency investigation
2. `get_trace_full` — for tag inspection (error messages, DB queries, HTTP URLs)
3. `get_service_map_for_trace` — visualize which services were involved

### When you don't have a trace ID and want to find outliers

1. `get_trace_outliers` — returns worst p99 latency by service/operation
2. Use returned `service` + `operation` in `search_traces`
3. Get trace IDs from results, proceed to analysis

---

## search_traces

Always include `environment` — queries without it may fail or be very slow.

```
search_traces(
  environment="production",
  services=["api-gateway"],
  operations=["GET /owners/{ownerId}"],
  tags={"error": "true"},
  startTimeMs=1743000000000,
  endTimeMs=1743003600000,
  limit=20
)
```

**Common tag filters:**
- `{"error": "true"}` — error traces only
- `{"http.status_code": "500"}` — 5xx responses
- `{"http.status_code": "404"}` — 404s (useful for detecting missing routes)
- `{"deployment.version": "v2.3.1"}` — traces from a specific deployment

**Interpreting results:**
- Each result has a `traceId`, `duration`, `rootServiceName`, `rootOperation`
- `duration` is in microseconds
- Results capped at 200 — if exactly 200 returned, use narrower filters or shorter time range

---

## get_trace_analysis

Returns a structured analysis of a trace's latency breakdown:

```json
{
  "traceID": "abc123",
  "totalDuration": 1234567,
  "spanCount": 42,
  "topLatencyContributors": [
    {
      "spanID": "span1",
      "operationName": "SELECT * FROM pets",
      "serviceName": "customers-service",
      "duration": 987654,
      "percentOfTrace": 80.0
    }
  ]
}
```

**Reading the contributors:**
- **One span at 70-90% of trace** = clear single bottleneck
- **Many spans from same service each at 5-10%** = N+1 query, fan-out, or serial loop
- **Service boundary span takes most time** = downstream dependency is slow
- **Root span is the largest** = overhead is in the calling service, not a downstream

---

## get_trace_full

Returns all spans with full tag details. Key fields per span:

| Field | Meaning |
|---|---|
| `spanID` | Unique span identifier |
| `operationName` | What this span does (e.g., `GET /owners`, `SELECT ...`) |
| `serviceName` | Which service emitted this span |
| `startTime` | Epoch milliseconds when span started |
| `duration` | Span duration in microseconds |
| `tags` | Array of `{key, value}` pairs |

**Tags to look for:**

| Tag key | Meaning |
|---|---|
| `error` | `"true"` if span errored |
| `error.message` | Error text |
| `http.method` | HTTP verb |
| `http.url` | Full URL called |
| `http.status_code` | Response status |
| `db.type` | Database type (mysql, postgresql, redis) |
| `db.statement` | SQL or query text |
| `db.instance` | Database name |
| `peer.service` | Name of called service |
| `span.kind` | client / server / producer / consumer |
| `deployment.version` | App version |

---

## Service Map Tools

### get_service_topology
Full environment service map. Use with a time range and optional environment filter.

```
get_service_topology(
  timeRange="2026-03-30T12:00:00Z/2026-03-30T13:00:00Z",
  tagFilters=[{"name": "sf_environment", "operator": "equals", "value": "production"}]
)
```

Returns `nodes` (services) and `edges` (service-to-service calls with latency data).
An edge with high P95 latency = potential bottleneck in that service-to-service call.

### get_service_dependencies
Direct dependencies of a single service. Faster than full topology when you only care
about one service's upstream/downstream.

```
get_service_dependencies(
  serviceName="api-gateway",
  timeRange="2026-03-30T12:00:00Z/2026-03-30T13:00:00Z"
)
```

### get_service_map_for_trace
The service map for a specific trace — which services were touched and in what order.
Useful for confirming the call path of a slow trace.

---

## Common Trace Patterns and What They Mean

### N+1 Query Pattern
**Symptom**: Many spans with identical `operationName` (e.g., `SELECT user WHERE id=?`)
**Evidence**: 20+ sequential DB spans each 2-5ms, totaling 100-500ms
**Fix**: Batch the query, add a JOIN, or cache results

### Slow Downstream Dependency
**Symptom**: One service-boundary span takes 80%+ of trace time
**Evidence**: `span.kind=client` span with high duration; `peer.service` points to the dependency
**Fix**: Investigate the dependency's own traces; check if it's having an incident

### DB Lock / Connection Pool Exhaustion
**Symptom**: DB spans with variable/intermittent high latency (not consistently slow)
**Evidence**: Same `db.statement` alternates between 1ms and 500ms
**Fix**: Check DB connection pool settings; look for long-running transactions holding locks

### Serial Chain (could be parallelized)
**Symptom**: Multiple independent service calls done sequentially
**Evidence**: In trace timeline, spans start after previous spans complete (no overlap)
**Fix**: Parallelize the downstream calls

### Cache Miss Pattern
**Symptom**: First request is slow, subsequent identical requests are fast
**Evidence**: Latency spike only on specific operation after cold start or invalidation
**Fix**: Pre-warm cache; increase TTL; check cache eviction

### Missing Instrumentation
**Symptom**: Long gap in trace waterfall with no child spans
**Evidence**: Parent span takes 2 seconds, but child spans only account for 200ms
**Fix**: Add instrumentation to the missing library/component

---

## get_trace_outliers

Returns the worst-performing service/operation combinations by p99 latency in a time window.
Use this when you want to find *where* to investigate without already knowing the service or trace.

```
get_trace_outliers(
  services=["api-gateway"],
  startTimeMs=1743000000000,
  endTimeMs=1743003600000,
  limit=10
)
```

Returns each outlier with:
- `service` — service name
- `operation` — operation name
- `p99LatencyMs` — p99 latency in milliseconds
- `environment` — APM environment

---

## list_trace_services

Lists all services that have reported traces in the last 48 hours.
Use this to:
- Confirm a service name before searching traces
- Discover what services exist in your environment
- Verify a service is still active after a suspected outage

```
list_trace_services(services=["api-gateway"])  # filter to specific services
list_trace_services()                           # all services
```

---

## References

- `skills/apm-traces/references/span-tags-reference.md` — Common span tag keys and their values
- `skills/apm-traces/references/search-patterns.md` — search_traces query patterns for common scenarios

### Cross-References
- For investigating a production incident using traces: **production-investigation** skill
- For running SignalFlow queries alongside trace analysis: **signalflow-queries** skill
- For creating dashboards with trace metrics: **create-splunk-dashboard** skill

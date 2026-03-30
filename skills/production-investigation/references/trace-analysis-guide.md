# Trace Analysis Guide

## Tool Selection

| Goal | Tool |
|------|------|
| Find traces matching criteria | `search_traces` |
| Get top latency contributors ranked | `get_trace_analysis` |
| Full span details + tags | `get_trace_full` |
| Find worst-latency service/op combos without a trace ID | `get_trace_outliers` |
| Visualize service-to-service call path for one trace | `get_service_map_for_trace` |

---

## Reading get_trace_analysis Output

`get_trace_analysis` returns:
- `totalDuration` — end-to-end trace duration in microseconds
- `spanCount` — total number of spans in the trace
- `topLatencyContributors` — top 5 spans by duration, each with:
  - `operationName` — what operation this span represents
  - `serviceName` — which service emitted it
  - `duration` — span duration in microseconds
  - `percentOfTrace` — this span's share of total trace time

**Interpreting contributors:**
- A span at 80%+ of total trace time = clear bottleneck
- Many spans from the same service each at 5–10% = N+1 or fan-out pattern
- A span at the service boundary that dominates = downstream dependency is slow

---

## Reading get_trace_full Output

`get_trace_full` returns all spans with:
- `spanID`, `operationName`, `serviceName`
- `startTime` (epoch ms), `duration` (microseconds)
- `tags` — array of `{key, value}` pairs

**Key tags to look for:**

| Tag | Meaning |
|-----|---------|
| `error` | "true" if span errored |
| `error.message` | Error message text |
| `http.status_code` | HTTP response code |
| `http.url` | URL called |
| `http.method` | GET, POST, etc. |
| `db.statement` | SQL/query text |
| `db.type` | Database type |
| `db.instance` | Database name |
| `peer.service` | Name of called downstream service |
| `span.kind` | client, server, producer, consumer |
| `deployment.version` | App version (if instrumented) |

**Waterfall analysis (manual, from startTime + duration):**
1. Sort spans by `startTime` ascending
2. The root span has no parent — it sets the total duration
3. Child spans should start after their parent and end before it
4. Gaps between a parent's start and its first child's start = overhead in the calling service
5. Sequential children (one starts after the previous ends) = serial execution — look for loops
6. Overlapping children = parallel execution — healthy

---

## Common Trace Patterns

### N+1 Query Pattern
- Many spans with the same `operationName` (e.g., `SELECT users WHERE id=?`)
- Each individually fast (1–5ms) but dozens of them = 50–500ms total
- Fix: batch the query or add a cache

### Slow Downstream
- One span at a service boundary takes 90% of the trace
- The downstream service's own p99 (via SignalFlow) will also be elevated
- Fix: investigate the downstream service separately; check its traces

### DB Lock / Queue
- A DB span with normal query time but long `startTime` gap from its parent
- The waiting time is before the span starts, invisible in the span itself
- Look for a pattern of variable latency on the same operation
- Fix: check DB lock contention, connection pool exhaustion

### Cold Start / Cache Miss
- First request to a service is very slow; subsequent ones are normal
- Check if the slow span is initialization code (e.g., config load, connection setup)
- Fix: warm-up calls, pre-initialization

### Missing Spans
- Gaps in the trace waterfall with no child spans
- Could be: unsampled service, uninstrumented library, async work outside trace context
- Look at `peer.service` tag on the calling span to identify what was called

---

## search_traces Tips

- Always include `environment` — searches without it may fail or be very slow
- Use `tags: {"error": "true"}` to find error traces
- Use `tags: {"http.status_code": "500"}` to find 5xx traces
- Combine `services` + `operations` to narrow to a specific endpoint
- Default time window is last 1 hour; extend `startTimeMs` for intermittent issues
- Results are capped at 200 — if you get exactly 200, there are more; narrow your filters

## get_trace_outliers Tips

- Returns service/operation combos with highest p99 latency in the window
- Use this when you don't have a specific trace ID yet
- The `service` and `operation` fields in results are the best candidates to pass into `search_traces`

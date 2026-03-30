---
name: signalflow-queries
description: >
  How to construct and execute SignalFlow programs correctly in Splunk Observability
  Cloud — query syntax, filter rules, aggregation functions, rollup methods, and
  common pitfalls. Use this skill when writing or debugging SignalFlow programs,
  querying metrics, or executing ad-hoc analytics.
  Trigger phrases: "run a SignalFlow query", "query my metrics", "execute signalflow",
  "what's my current CPU", "show me the error rate", "how do I filter by service",
  "SignalFlow syntax", "signalflow error", "metric query", "ad-hoc query",
  "query the last hour", "how do I group by service", "signalflow not returning data",
  or any request to write, run, or debug a SignalFlow program.
metadata:
  version: "1.0.0"
allowed-tools:
  - mcp__splunk-observability__execute_signalflow
  - mcp__splunk-observability__search_metrics
  - mcp__splunk-observability__get_metric_metadata
  - mcp__splunk-observability__search_metric_time_series
  - mcp__splunk-observability__get_mts_metadata
  - mcp__splunk-observability__search_dimensions
  - mcp__splunk-observability__get_dimension
  - AskUserQuestion
---

# SignalFlow Queries

SignalFlow is Splunk Observability's real-time analytics language. This skill covers
correct syntax, filter rules, aggregation patterns, and how to interpret results.

---

## Core Syntax

```
data('metric.name', filter=filter('key', 'value'))
  .<transformation>()
  .publish(label='my_label')
```

Every program must end with `.publish()` to return results.

---

## Filter Rules (Critical — common mistakes here)

### Rule 1: ONE filter per data() call, via `filter=` keyword
```
# CORRECT
data('metric', filter=filter('sf_service', 'api-gateway'))

# WRONG — second positional arg is treated as rollup, causes API error
data('metric', filter('sf_service', 'api-gateway'), filter('error', 'true'))
```

### Rule 2: Combine multiple filters with `and`
```
# CORRECT
data('metric',
     filter=filter('sf_service', 'api-gateway') and filter('error', 'true'))

# WRONG
data('metric', filter=filter('sf_service', 'api-gateway'), filter=filter('error', 'true'))
```

### Rule 3: Multiple values in one filter = OR
```
# Matches api-gateway OR vets-service
data('metric', filter=filter('sf_service', 'api-gateway', 'vets-service'))
```

### Rule 4: NOT filter
```
data('metric', filter=not filter('sf_environment', 'staging'))
```

### Rule 5: Wildcard matching
```
# Matches any service starting with "api-"
data('metric', filter=filter('sf_service', 'api-*'))
```

---

## Aggregation Functions

### Spatial aggregation (across time series)
Reduce multiple time series into one:

| Function | Effect |
|---|---|
| `.mean()` | Average across all matching time series |
| `.sum()` | Sum across all matching time series |
| `.max()` | Maximum across all matching time series |
| `.min()` | Minimum across all matching time series |
| `.count()` | Count of active time series |
| `.mean(by=['key'])` | Mean, grouped by dimension key |
| `.sum(by=['sf_service'])` | Sum, grouped by service |

### Temporal aggregation (over time windows)
Smooth a time series over a rolling window:

| Function | Effect |
|---|---|
| `.mean(over='5m')` | Rolling 5-minute average |
| `.sum(over='1h')` | Rolling 1-hour sum |
| `.max(over='10m')` | Rolling max |
| `.percentile(pct=99, over='5m')` | Rolling p99 |

### Chaining spatial + temporal
```
# Mean across services, then smoothed over 5 minutes
data('cpu.utilization')
  .mean(by=['host'])   # spatial: group by host
  .mean(over='5m')     # temporal: smooth each host's line
  .publish()
```

---

## Common Programs

### Current metric value (single number)
```
data('cpu.utilization',
     filter=filter('host', 'web-01'))
  .mean()
  .publish(label='CPU')
```

### Time series by dimension
```
data('service.request.duration.ns.p99',
     filter=filter('sf_environment', 'production'))
  .mean(by=['sf_service'])
  .publish(label='P99 by Service')
```

### Rate of change
```
data('spans.count',
     filter=filter('sf_service', 'api-gateway'))
  .sum()
  .rate()
  .publish(label='Requests per second')
```

### Delta (difference between consecutive values)
```
data('my.counter')
  .sum()
  .delta()
  .publish(label='Delta')
```

### Arithmetic between two streams
```
errors = data('spans.count',
              filter=filter('sf_service', 'api-gateway') and filter('error', 'true'))
           .sum()
total  = data('spans.count',
              filter=filter('sf_service', 'api-gateway'))
           .sum()
(errors / total * 100).publish(label='Error Rate %')
```

### Top N by value (use in List charts)
```
data('service.request.duration.ns.p99')
  .mean(by=['sf_service'])
  .top(count=10)
  .publish(label='Top 10 Slowest Services')
```

### Bottom N (slowest by negative: worst performers)
```
data('service.request.duration.ns.p99')
  .mean(by=['sf_service'])
  .bottom(count=5)
  .publish(label='5 Fastest Services')
```

---

## Rollup Methods

Rollup controls how raw data points are aggregated within each resolution window.

| Rollup | Meaning |
|---|---|
| `rollup='average'` | Average of data points in window (default for gauges) |
| `rollup='sum'` | Sum of data points (default for counters) |
| `rollup='max'` | Maximum value in window |
| `rollup='min'` | Minimum value in window |
| `rollup='latest'` | Most recent value in window |
| `rollup='rate'` | Change per second |

```
data('cpu.utilization', rollup='average').mean().publish()
data('spans.count', rollup='sum').sum().publish()
```

---

## Querying Events (Custom Events)

Events use the `events()` function, not `data()`:

```
events(eventType='deployment.started').publish(label='Deployments')
```

With filter:
```
events(eventType='deployment.started',
       filter=filter('sf_environment', 'production'))
  .publish(label='Production Deployments')
```

Note: Events appear as event messages in the SignalFlow response, not as numeric data points.
Check `events` in the response (not `dataPoints`) when querying events.

---

## Discovering Metrics and Dimensions

Before writing a program, verify your metric and dimension values exist:

1. `search_metrics` with `query='cpu*'` → find metric names matching a pattern
2. `get_metric_metadata` with `metric_name='cpu.utilization'` → see metric type and description
3. `search_dimensions` with `query='key:sf_service AND value:api*'` → find real dimension values
4. `search_metric_time_series` with `query='sf_metric:cpu.utilization AND sf_service:api-gateway'` → confirm a specific MTS exists

Use these tools when `execute_signalflow` returns `hasData: false`.

---

## Interpreting execute_signalflow Results

The response contains:
- `hasData` — boolean; false means no time series matched
- `dataPointCount` — number of data points returned
- `dataPoints` — array of `{tsId, value, timestampMs, properties}`
  - `properties` — the dimension key-values for that time series (e.g., `sf_service`, `sf_environment`)
- `events` — SignalFlow control messages (done, error, metadata)

**If hasData is false:**
1. Check metric name — `search_metrics` to confirm it exists
2. Check filter values — `search_dimensions` to find real values
3. Try without any filter first; add filters back one by one
4. Check time range — default is last 1 hour; metric may not have recent data

**If dataPointCount is very high:**
- Add `.mean(by=['sf_service'])` to aggregate
- Narrow filters to reduce cardinality

---

## Time Range Reference

`execute_signalflow` `start` and `stop` are Unix timestamps in milliseconds.

Common values:
- Last 5 minutes: `start = now - 300000`
- Last 1 hour: `start = now - 3600000` (default)
- Last 24 hours: `start = now - 86400000`
- Last 7 days: `start = now - 604800000`

You can also use the `immediate=true` flag to get only data up to the current moment
(prevents waiting for future data windows to close).

---

## References

- `skills/signalflow-queries/references/function-reference.md` — Complete SignalFlow function list
- `skills/signalflow-queries/references/common-metrics.md` — Common Splunk Observability metric names

### Cross-References
- For building dashboards with SignalFlow: **create-splunk-dashboard** skill
- For creating detectors using SignalFlow detect(): **detectors-and-alerts** skill
- For APM-specific metrics: **apm-traces** skill

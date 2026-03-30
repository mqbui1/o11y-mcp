---
name: production-investigation
description: >
  Structured workflows for investigating production incidents in Splunk Observability
  Cloud — triaging active alerts, correlating metrics with traces, pinpointing root
  causes using the service map, and verifying hypotheses with SignalFlow.
  Trigger phrases: "investigate production issue", "debug latency spike",
  "find root cause", "analyze traces", "debug an outage", "why is my service slow",
  "errors are increasing", "health check", "alert is firing", "incident triage",
  "check active alerts", "what's broken", "service is down", "high error rate",
  "p99 is spiking", "investigate the incident", or any request to investigate,
  debug, or root-cause a production problem in Splunk Observability.
metadata:
  version: "1.0.0"
allowed-tools:
  - mcp__splunk-observability__list_incidents
  - mcp__splunk-observability__get_incident
  - mcp__splunk-observability__list_detectors
  - mcp__splunk-observability__get_detector
  - mcp__splunk-observability__get_detector_incidents
  - mcp__splunk-observability__execute_signalflow
  - mcp__splunk-observability__search_traces
  - mcp__splunk-observability__get_trace_full
  - mcp__splunk-observability__get_trace_analysis
  - mcp__splunk-observability__get_trace_outliers
  - mcp__splunk-observability__get_service_topology
  - mcp__splunk-observability__get_service_dependencies
  - mcp__splunk-observability__search_service_map
  - mcp__splunk-observability__get_service_map_for_trace
  - mcp__splunk-observability__list_trace_services
  - mcp__splunk-observability__search_metrics
  - mcp__splunk-observability__search_events
  - mcp__splunk-observability__clear_incident
  - AskUserQuestion
---

# Splunk Observability Production Investigation

Structured workflows for debugging production incidents. The MCP tools document their
own parameters — this skill focuses on the *sequence* of tool calls and how to
*interpret* results to reach a root cause.

## The Core Investigation Loop

**Orient → Characterize → Localize → Drill → Verify → Record**

Never skip steps because "the cause seems obvious." Each step takes less than a minute
and routinely surfaces secondary causes or disconfirms premature hypotheses.

---

## Investigation Workflow

### Step 1: Orient — What's firing?

1. `list_incidents` → Are there active incidents? What detectors fired?
2. `list_detectors` (name filter on the fired detector) → What condition triggered?
3. `get_detector_incidents` for the specific detector → How long has it been firing?
4. `search_events` (last 30–60 min) → Any deployment events or config changes near the incident start?

**What to look for:**
- Severity (Critical vs Minor) — frames how fast to move
- Which service/environment the detector watches
- Whether this detector has fired recently before (pattern vs one-off)
- Deployment or change events close to the incident start time

---

### Step 2: Characterize — What shape is the problem?

Run a broad SignalFlow query to see the current state of the affected metric.

**Latency spike:**
```
data('service.request.duration.ns.p99',
     filter=filter('sf_environment', 'production'))
  .mean(by=['sf_service'])
  .publish()
```

**Error surge:**
```
data('spans.count',
     filter=filter('sf_environment', 'production') and filter('error', 'true'))
  .sum(by=['sf_service'])
  .publish()
```

**Traffic drop / throughput:**
```
data('spans.count',
     filter=filter('sf_environment', 'production'))
  .sum(by=['sf_service'])
  .publish()
```

Also call `get_service_topology` for the affected environment's time range — it shows
P95 durations and error rates between services and can immediately reveal which
dependency is degraded.

---

### Step 3: Localize — Which service or operation?

Once you know the symptom type, break it down:

1. **By service**: Group the SignalFlow query by `sf_service` — which service has the anomaly?
2. **By operation**: Narrow to the affected service, group by `sf_operation` — which endpoint?
3. `get_service_dependencies` for the affected service — which upstream/downstream services
   could be causing or amplifying the problem?

**Dependency failure pattern:**
- `get_service_topology` shows elevated P95 on a dependency edge → that dependency is the bottleneck
- `search_service_map` filtered to the affected service confirms the call path

---

### Step 4: Drill into traces

After localizing to a service and operation:

1. `search_traces` with `environment`, `services`, and optionally `tags: {"error": "true"}` or
   `tags: {"http.status_code": "500"}` — find representative traces
2. `get_trace_analysis` on a trace ID — returns top latency contributors ranked by duration
3. `get_trace_full` for deep span inspection — operation names, service names, tags, duration

**What to look for in traces:**
- Spans with disproportionate duration vs their siblings (the bottleneck span)
- A long chain of sequential DB or external calls (N+1 query pattern)
- Error spans — check span tags for `error.message`, `db.statement`, `http.url`
- Service boundaries where time is "lost" — gap between parent ending and child starting
- Repeated operation names with high cumulative time (serial loops)

For latency outliers without a specific trace ID, use `get_trace_outliers` to find the
worst-offending service/operation combinations in the time window.

---

### Step 5: Verify the hypothesis

After forming a hypothesis from the service map + trace analysis:

1. Run a SignalFlow query **WITH** the suspected cause filtered in — confirm the metric is elevated
2. Run the same query **WITHOUT** it (as a control) — confirm it's healthy
3. If metrics diverge, the hypothesis is confirmed

**Example — verifying a bad deployment:**
```
# With new version
data('service.request.duration.ns.p99',
     filter=filter('sf_service', 'api-gateway') and filter('deployment.version', 'v2.3.1'))
  .mean().publish(label='new_version')

# Baseline (old version)
data('service.request.duration.ns.p99',
     filter=filter('sf_service', 'api-gateway') and filter('deployment.version', 'v2.2.9'))
  .mean().publish(label='old_version')
```

**Example — verifying a downstream dependency:**
```
data('service.request.duration.ns.p99',
     filter=filter('sf_service', 'payments-service'))
  .mean().publish(label='payments_p99')
```

---

### Step 6: Resolve or escalate

- If root cause confirmed and fix available: apply fix, monitor metrics, `clear_incident` once resolved
- If root cause confirmed but fix needs a team: summarize findings with evidence (metric values, trace IDs, time of onset)
- If inconclusive: escalate with what was ruled out and what to investigate next

---

## Investigation Patterns

### Latency Spike
Service topology → identify slow edge → SignalFlow p99 by service/operation → `get_trace_outliers` → `get_trace_analysis` on slow trace → verify with filtered query

### Error Surge
SignalFlow error count by service → `search_traces` with `error=true` → `get_trace_full` on errored trace → check error span tags → verify with filtered query

### Deployment Regression
Check `search_events` for recent deployments → SignalFlow p99 by `deployment.version` → `search_traces` filtered to new version → `get_trace_analysis` → verify old vs new

### Dependency Failure
`get_service_topology` → elevated edge latency → `get_service_dependencies` for affected service → SignalFlow on the dependency's own metrics → `search_service_map` to confirm call path

### Traffic Drop / Data Loss
SignalFlow `spans.count` by service → identify which service stopped reporting → check `list_incidents` for infra alerts → check `search_events` for config/deploy changes

---

## SignalFlow Quick Reference

Key APM metrics:
- `service.request.duration.ns.p99` — request latency (nanoseconds)
- `service.request.duration.ns.p50` — median latency
- `spans.count` — span/request throughput
- `spans.count` with `filter('error', 'true')` — error count

Common dimensions to group or filter by:
- `sf_service` — service name
- `sf_operation` — operation/endpoint name
- `sf_environment` — APM environment
- `error` — "true"/"false"
- `http.status_code` — HTTP status
- `deployment.version` — deployment version tag (if instrumented)

Time windows: default to last 1 hour for active incidents; extend to 4–24 hours for intermittent issues.

---

## When Results Are Empty or Unclear

- **No traces returned**: Check `list_trace_services` to confirm the service exists; verify environment name; expand time range
- **SignalFlow returns no data**: Confirm metric name with `search_metrics`; check dimension values with `search_dimensions`
- **Topology shows no edges**: Use a wider time range; verify environment tag filter
- **Incident cleared itself**: Check `list_incidents` with `includeResolved=true`

---

## References

- `skills/production-investigation/references/signalflow-patterns.md` — Common SignalFlow programs for APM investigation
- `skills/production-investigation/references/trace-analysis-guide.md` — Interpreting span tags and latency contributors
- `skills/production-investigation/references/incident-playbooks.md` — Step-by-step playbooks for each incident type

### Cross-References
- For building a dashboard to track the incident: **create-splunk-dashboard** skill
- For creating a detector to catch this again: **detectors-and-alerts** skill
- For ad-hoc metric queries: **signalflow-queries** skill
- For deep trace analysis: **apm-traces** skill

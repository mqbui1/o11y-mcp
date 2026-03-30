---
name: detectors-and-alerts
description: >
  Decision heuristics for designing, creating, and interpreting Splunk Observability
  detectors and alert rules — what conditions to detect, how to write SignalFlow
  detect() programs, how to choose severity, and how to configure muting rules.
  Load this skill before calling create_detector, list_detectors, or list_incidents.
  Trigger phrases: "create a detector", "set up an alert", "create an alert",
  "configure alerting", "detector for my service", "alert when latency is high",
  "alert on error rate", "set up a muting rule", "mute alerts", "check detectors",
  "which detectors are firing", "review my alerts", "alert fatigue",
  "tune my detector", "update detector threshold", or any request about
  creating, reviewing, or managing Splunk Observability detectors and alerts.
metadata:
  version: "1.0.0"
allowed-tools:
  - mcp__splunk-observability__list_detectors
  - mcp__splunk-observability__get_detector
  - mcp__splunk-observability__create_detector
  - mcp__splunk-observability__update_detector
  - mcp__splunk-observability__delete_detector
  - mcp__splunk-observability__get_detector_incidents
  - mcp__splunk-observability__list_incidents
  - mcp__splunk-observability__get_incident
  - mcp__splunk-observability__clear_incident
  - mcp__splunk-observability__list_muting_rules
  - mcp__splunk-observability__create_muting_rule
  - mcp__splunk-observability__delete_muting_rule
  - mcp__splunk-observability__execute_signalflow
  - mcp__splunk-observability__search_metrics
  - mcp__splunk-observability__list_integrations
  - AskUserQuestion
---

# Splunk Observability Detectors and Alerts

Guidance for designing effective detectors (alerts) in Splunk Observability Cloud.
The MCP tools document their own parameters — this skill focuses on *designing*
correct detection programs, *choosing* thresholds and severities, and *interpreting*
what firing incidents mean.

---

## Detector vs Muting Rule — When to Use Which

| Situation | Use |
|---|---|
| Alert when a metric exceeds a threshold | Detector |
| Alert when a metric drops below a threshold | Detector |
| Alert when a metric anomaly is detected | Detector |
| Suppress alerts during maintenance window | Muting Rule |
| Suppress noisy alerts while investigating | Muting Rule |
| Alert is firing but it's a known false positive | Clear Incident + Muting Rule |

---

## Detector Design Workflow

### Step 1: Understand the metric

1. `search_metrics` — confirm the metric name exists
2. `execute_signalflow` with a simple `data('metric').mean().publish()` — see the current value and range
3. Note the natural baseline: min, max, and typical operating value

### Step 2: Choose the detection strategy

| Strategy | When to use | SignalFlow pattern |
|---|---|---|
| Static threshold | Known safe limit (e.g., CPU > 90%) | `when(A > 90)` |
| Dynamic threshold (vs rolling mean) | No fixed limit; detect spikes vs history | `when(A > B * 1.5)` |
| Rate of change | Catch sudden changes (not sustained highs) | `when(A.delta() > threshold)` |
| Absence / data gap | Alert when metric stops reporting | `when(not A)` or `lasting` with `at_least` |

### Step 3: Write the SignalFlow program

Key rules (auto-corrected by server, but write correctly):
- `detect()` requires a boolean: `detect(when(A > threshold))`
- Multiple filters must use `and`: `filter=filter('sf_service','x') and filter('error','true')`
- `lasting` belongs inside `when()`: `detect(when(A > B, lasting=duration('5m')))`
- `filter()` with multiple values is OR: `filter('sf_service', 'svc-a', 'svc-b')`
- Use `duration()` wrapper: `lasting=duration('5m')` not `lasting='5m'`

### Step 4: Validate before creating

Run the SignalFlow program with `execute_signalflow` to confirm:
- It returns data (`hasData: true`)
- The current values make sense relative to your threshold
- The program doesn't error

### Step 5: Show the proposed detector to the user

Before calling `create_detector`, display:
- Detector name and description
- The full SignalFlow program
- The threshold value and why it was chosen
- Severity and label for each rule
- Whether you recommend a lasting duration and why

End with: "Here's the detector I'd create. Shall I go ahead?"

---

## Severity Selection

| Severity | Meaning | Typical use |
|---|---|---|
| `Critical` | Immediate action required; system may be down | P99 > 10x baseline, error rate > 50% |
| `Major` | Significant degradation; page the on-call | P99 > 5x baseline, error rate > 10% |
| `Minor` | Degraded but not failing; notify team | P99 > 2x baseline, error rate > 2% |
| `Warning` | Early warning; trending toward a problem | P99 > 1.5x baseline, error rate > 1% |
| `Info` | Informational; no action needed | Deployment events, config changes |

Use multiple rules in one detector for tiered alerting:
```json
[
  {"severity": "Warning",  "detectLabel": "warn",  "name": "Latency Warning"},
  {"severity": "Critical", "detectLabel": "crit",  "name": "Latency Critical"}
]
```
Each rule has a matching `publish(label='...')` call in the SignalFlow program.

---

## Common Detector Patterns

### Static threshold — latency
```
A = data('service.request.duration.ns.p99',
         filter=filter('sf_service', 'api-gateway') and filter('sf_environment', 'production'))
      .mean()
detect(when(A > 500000000, lasting=duration('5m'))).publish(label='high_latency')
```
*Rule: severity=Major, detectLabel='high_latency'*

Note: `service.request.duration.ns.p99` is in nanoseconds. 500000000 ns = 500ms.

### Dynamic threshold — latency spike vs rolling mean
```
f = filter('sf_service', 'api-gateway') and filter('sf_environment', 'production')
A = data('service.request.duration.ns.p99', filter=f).mean().mean(over='5m')
B = data('service.request.duration.ns.p99', filter=f).mean().mean(over='1h')
detect(when(A > B * 3, lasting=duration('5m'))).publish(label='latency_spike')
```
*Rule: severity=Major, detectLabel='latency_spike'*

### Error rate threshold
```
f = filter('sf_service', 'api-gateway') and filter('sf_environment', 'production')
errors = data('spans.count', filter=f and filter('error', 'true')).sum()
total  = data('spans.count', filter=f).sum()
rate   = (errors / total * 100).mean(over='5m')
detect(when(rate > 5, lasting=duration('3m'))).publish(label='high_error_rate')
```
*Rule: severity=Critical, detectLabel='high_error_rate'*

### Traffic drop (absolute)
```
A = data('spans.count',
         filter=filter('sf_service', 'api-gateway') and filter('sf_environment', 'production'))
      .sum().mean(over='5m')
detect(when(A < 10, lasting=duration('5m'))).publish(label='low_traffic')
```
*Rule: severity=Major, detectLabel='low_traffic'*

### Traffic drop (relative to baseline)
```
f = filter('sf_service', 'api-gateway')
current  = data('spans.count', filter=f).sum().mean(over='5m')
baseline = data('spans.count', filter=f).sum().mean(over='1h')
detect(when(current < baseline * 0.5, lasting=duration('5m'))).publish(label='traffic_drop')
```
*Rule: severity=Major, detectLabel='traffic_drop'*

### CPU saturation
```
A = data('cpu.utilization').mean(by=['host']).mean(over='5m')
detect(when(A > 90, lasting=duration('10m'))).publish(label='high_cpu')
```
*Rule: severity=Critical, detectLabel='high_cpu'*

### Multi-tier (warning + critical)
```
f = filter('sf_service', 'api-gateway') and filter('sf_environment', 'production')
A = data('service.request.duration.ns.p99', filter=f).mean().mean(over='5m')
B = data('service.request.duration.ns.p99', filter=f).mean().mean(over='1h')
detect(when(A > B * 2, lasting=duration('5m'))).publish(label='warn')
detect(when(A > B * 5, lasting=duration('5m'))).publish(label='crit')
```
*Rules: [{severity=Warning, detectLabel='warn'}, {severity=Critical, detectLabel='crit'}]*

---

## Interpreting Active Incidents

When `list_incidents` shows firing incidents:

- **incidentId** — use with `get_incident` for full details
- **severity** — Critical/Major = investigate now; Minor/Warning = schedule investigation
- **detectLabel** — maps to the `publish(label='...')` in the detector's SignalFlow
- **detector name** — use `list_detectors` with name filter to find the detector definition
- **triggeredWhileMuted** — if true, a muting rule was active when this fired

For each Critical incident, immediately open the **production-investigation** skill workflow.

---

## Muting Rules

Use muting rules to suppress alerts during planned maintenance, deployments, or known
false-positive windows.

### Create a muting rule
```json
{
  "description": "Maintenance window 2026-04-01 02:00-04:00 UTC",
  "filters": [
    {"property": "sf_environment", "propertyValue": "production"}
  ],
  "startTime": 1743469200000,
  "stopTime":  1743476400000
}
```

**Filter properties** — match any dimension that appears in the detector's SignalFlow:
- `"sf_environment"` — mute for a specific environment
- `"sf_service"` — mute for a specific service
- `"detector_name"` — mute a specific detector by name
- `"severity"` — mute only certain severities

### Scope muting carefully
- Always set `stopTime` — open-ended muting rules silently suppress real incidents
- Prefer narrow filters (specific service or environment) over broad ones
- Review `list_muting_rules` before creating a new one to avoid overlapping rules

---

## Tuning Detectors to Reduce Alert Fatigue

1. `get_detector_incidents` → how often has this detector fired in the last week?
2. `execute_signalflow` with the detector's program → what does the current value vs threshold look like?
3. If firing too often:
   - Increase the threshold or the `lasting` duration
   - Add a `mean(over='5m')` smoothing before the detect()
   - Add environment/service filters if firing on non-critical services
4. If never firing (potentially broken):
   - Confirm the metric is still being reported with `execute_signalflow`
   - Check that filter values (service name, environment) still match real dimensions

---

## References

- `skills/detectors-and-alerts/references/signalflow-detect-patterns.md` — Full library of detect() programs
- `skills/detectors-and-alerts/references/severity-guide.md` — Threshold selection guidance by metric type
- `skills/detectors-and-alerts/references/muting-examples.md` — Muting rule examples for common scenarios

### Cross-References
- For investigating a firing incident: **production-investigation** skill
- For creating a dashboard to track alerting trends: **create-splunk-dashboard** skill
- For SignalFlow syntax reference: **signalflow-queries** skill

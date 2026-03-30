---
name: create-splunk-dashboard
description: >
  Design and create a dashboard in Splunk Observability Cloud with charts powered
  by SignalFlow. Use this skill to build service health dashboards, incident
  investigation boards, feature dashboards, or any custom visualization.
  Trigger phrases: "create a dashboard", "make a dashboard", "build a dashboard",
  "create a chart", "set up monitoring dashboard", "golden signals dashboard",
  "service health dashboard", "visualize metrics", "dashboard for my service",
  "add a chart to the dashboard", "update the dashboard", "create a Splunk dashboard",
  or any request to design and create a Splunk Observability dashboard or chart.
metadata:
  version: "1.0.0"
allowed-tools:
  - mcp__splunk-observability__list_dashboards
  - mcp__splunk-observability__get_dashboard
  - mcp__splunk-observability__create_dashboard
  - mcp__splunk-observability__update_dashboard
  - mcp__splunk-observability__delete_dashboard
  - mcp__splunk-observability__list_dashboard_groups
  - mcp__splunk-observability__get_dashboard_group
  - mcp__splunk-observability__create_chart
  - mcp__splunk-observability__get_chart
  - mcp__splunk-observability__update_chart
  - mcp__splunk-observability__delete_chart
  - mcp__splunk-observability__list_charts_in_dashboard
  - mcp__splunk-observability__execute_signalflow
  - mcp__splunk-observability__search_metrics
  - mcp__splunk-observability__list_detectors
  - mcp__splunk-observability__list_trace_services
  - mcp__splunk-observability__get_service_topology
  - AskUserQuestion
---

# Create a Splunk Observability Dashboard

Build dashboards in Splunk Observability Cloud using `create_chart` + `create_dashboard`
(or `update_dashboard` to add charts to an existing one).

Think carefully about the dashboard's **purpose** before designing it:

- **Service health** — timeless view of golden signals; no investigation opinions; usable any time
- **Incident investigation** — snapshot of the incident window; include hypotheses and annotations
- **Feature/business** — usage trends, business KPIs; longer time range (24h–7d)
- **On-call** — quick overall health summary; wide charts for fast scanning

---

## Workflow

### Step 1: Understand what exists

1. `list_dashboards` (name filter) → is there already a dashboard for this service/topic?
2. `list_dashboard_groups` → which group should the new dashboard go into?
3. `list_trace_services` → confirm service names exist in APM (for APM dashboards)
4. `search_metrics` → confirm metric names exist (for infra/custom metric dashboards)

---

### Step 2: Plan the charts

Good service health dashboards cover the **four golden signals**:
1. **Latency** — P99, P50, heatmap of request duration
2. **Errors** — error count or error rate (errors/total)
3. **Traffic** — request rate (spans per minute)
4. **Saturation** — CPU, memory, or queue depth (if available)

For each chart, decide:
- **Chart type**: `TimeSeriesChart` (line/area/column), `SingleValue` (stat), `Heatmap`, `List`, `Text`
- **Time range**: relative (e.g., last 1 hour = 3600000ms) or absolute
- **Grouping**: by `sf_service`, `sf_operation`, `host`, etc.
- **Width/height**: on a 12-column grid — stat charts can be 2–3 wide; heatmaps 12 wide

Aim for 6–12 charts. Text panels (no programText needed) are good for descriptions and links.

**Always show the proposed chart list to the user before creating anything.**

For each proposed chart, display:
- Name and chart type
- The SignalFlow program that will power it
- What question it answers

End with: "Here's the dashboard I'd create. Shall I go ahead?"

---

### Step 3: Validate SignalFlow programs

Run `execute_signalflow` for each non-trivial program before creating charts.

Check:
- `hasData: true` — the program returns data
- `dataPointCount > 0` — at least one time series came back
- The `properties` on returned data points confirm correct dimensions (right service, environment, etc.)

If `hasData: false`: check metric name with `search_metrics`; check dimension values with `search_dimensions`.

---

### Step 4: Create charts

Call `create_chart` for each chart. Required fields:
- `name` — descriptive name shown on the chart tile
- `programText` — SignalFlow program
- `options.type` — chart type (see below)

Save each returned chart ID — you'll need them for the dashboard.

**Chart type reference:**

| options.type | Best for |
|---|---|
| `TimeSeriesChart` | Line/area/column trends over time |
| `SingleValue` | Current value stat, big number display |
| `Heatmap` | Distribution of values across dimensions |
| `List` | Tabular ranking (top N services by latency) |
| `Event` | Event overlay (deployments, incidents) |
| `Text` | Markdown description panel (no programText needed) |

**TimeSeriesChart options:**
```json
{
  "type": "TimeSeriesChart",
  "defaultPlotType": "LineChart",
  "time": {"type": "relative", "range": 3600000}
}
```
`defaultPlotType` options: `"LineChart"`, `"AreaChart"`, `"ColumnChart"`

**SingleValue options:**
```json
{
  "type": "SingleValue",
  "time": {"type": "relative", "range": 3600000}
}
```

**Heatmap options:**
```json
{
  "type": "Heatmap",
  "time": {"type": "relative", "range": 3600000}
}
```

**Text panel (no programText):**
```json
{
  "type": "Text",
  "markdown": "## My Service\nOwned by Platform team. [Runbook](https://...)"
}
```
For Text charts, pass `programText=""` and put content in `options.markdown`.

---

### Step 5: Create or update the dashboard

**New dashboard:**
```json
{
  "name": "API Gateway — Service Health",
  "description": "Golden signals for api-gateway. Updated automatically.",
  "charts": [
    {"chartId": "abc123", "row": 0, "column": 0,  "width": 12, "height": 1},
    {"chartId": "def456", "row": 1, "column": 0,  "width": 4,  "height": 1},
    {"chartId": "ghi789", "row": 1, "column": 4,  "width": 4,  "height": 1},
    {"chartId": "jkl012", "row": 1, "column": 8,  "width": 4,  "height": 1},
    {"chartId": "mno345", "row": 2, "column": 0,  "width": 12, "height": 2}
  ],
  "tags": ["team:platform", "service:api-gateway"]
}
```

**Adding charts to an existing dashboard:**
1. `get_dashboard` → get existing chart list
2. `list_charts_in_dashboard` → get current chart IDs and positions
3. `update_dashboard` with the merged chart list (existing + new)

**Grid layout guidance:**
- Total width = 12 columns
- `row` increments by `height` of the previous row
- Text/description panels: full width (12), height 1
- Stat (SingleValue) charts: width 3–4, can be placed side by side
- Time series: width 6–12 depending on importance
- Heatmaps: full width (12), height 2

---

### Step 6: Link the dashboard

After creation, the response includes the dashboard `id`. Construct the URL:
`https://app.{realm}.signalfx.com/#/dashboard/{dashboard_id}`

Share this URL with the user.

---

## SignalFlow for Common Charts

### P99 Latency (time series, by service)
```
data('service.request.duration.ns.p99',
     filter=filter('sf_environment', 'production'))
  .mean(by=['sf_service'])
  .publish(label='P99 Latency (ns)')
```

### Error Rate % (time series)
```
errors = data('spans.count',
              filter=filter('sf_service', 'api-gateway') and filter('error', 'true'))
           .sum()
total  = data('spans.count',
              filter=filter('sf_service', 'api-gateway'))
           .sum()
(errors / total * 100).publish(label='Error Rate %')
```

### Request Rate (time series)
```
data('spans.count',
     filter=filter('sf_service', 'api-gateway'))
  .sum().publish(label='Requests/min')
```

### Current P99 (single value)
```
data('service.request.duration.ns.p99',
     filter=filter('sf_service', 'api-gateway'))
  .mean()
  .publish(label='P99 Latency')
```

### Top N slowest operations (list)
```
data('service.request.duration.ns.p99',
     filter=filter('sf_service', 'api-gateway'))
  .mean(by=['sf_operation'])
  .publish(label='P99 by Operation')
```

### Deployment / custom events overlay
```
events(eventType='deployment.started',
       filter=filter('sf_environment', 'production'))
  .publish(label='Deployments')
```

---

## References

- `skills/create-splunk-dashboard/references/chart-options.md` — Full chart options reference
- `skills/create-splunk-dashboard/references/layout-guide.md` — Grid layout examples and patterns
- `skills/create-splunk-dashboard/references/signalflow-cookbook.md` — Ready-to-use SignalFlow programs for dashboards

### Cross-References
- For investigating an active incident: **production-investigation** skill
- For creating detectors/alerts: **detectors-and-alerts** skill
- For SignalFlow query construction: **signalflow-queries** skill

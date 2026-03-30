# Chart Options Reference

## TimeSeriesChart

```json
{
  "type": "TimeSeriesChart",
  "defaultPlotType": "LineChart",
  "time": {"type": "relative", "range": 3600000},
  "axes": [
    {
      "label": "Latency (ns)",
      "lowWatermark": 0
    }
  ],
  "legend": {
    "enabled": true,
    "fields": [
      {"property": "sf_service", "enabled": true},
      {"property": "sf_operation", "enabled": true}
    ]
  },
  "colorTheme": "Default"
}
```

`defaultPlotType` values:
- `"LineChart"` — line graph (best for smooth metrics)
- `"AreaChart"` — filled area (good for rate/throughput)
- `"ColumnChart"` — bar chart (good for counts)

Time range:
- Relative: `{"type": "relative", "range": <ms>}` — e.g., 3600000 = 1h, 86400000 = 24h
- Absolute: `{"type": "absolute", "start": <epoch_ms>, "end": <epoch_ms>}`

---

## SingleValue

```json
{
  "type": "SingleValue",
  "time": {"type": "relative", "range": 3600000},
  "colorBy": "Metric",
  "secondaryVisualization": "Sparkline",
  "showSparkLine": true
}
```

`secondaryVisualization` values: `"None"`, `"Radial"`, `"Linear"`, `"Sparkline"`

---

## Heatmap

```json
{
  "type": "Heatmap",
  "time": {"type": "relative", "range": 3600000},
  "groupBy": ["sf_service"],
  "colorTheme": "Default",
  "colorScale": [
    {"thresholdType": "LT", "gt": 0,     "color": "green"},
    {"thresholdType": "LT", "gt": 100,   "color": "yellow"},
    {"thresholdType": "LT", "gt": 1000,  "color": "red"}
  ]
}
```

---

## List

```json
{
  "type": "List",
  "time": {"type": "relative", "range": 3600000},
  "sortBy": "-value"
}
```

`sortBy`: `"-value"` (descending), `"+value"` (ascending), `"-sf_service"` (alphabetical desc)

---

## Event

```json
{
  "type": "Event",
  "time": {"type": "relative", "range": 3600000}
}
```

Use with `events(eventType='...')` SignalFlow programs.

---

## Text

```json
{
  "type": "Text",
  "markdown": "## Service Name\n\nDescription here. [Runbook](https://...)"
}
```

When creating a Text chart, pass `programText: ""` (empty string) and put content in `options.markdown`.

---

## Dashboard Chart Positioning

The `charts` array in `create_dashboard` / `update_dashboard` uses:
```json
{
  "chartId": "<id>",
  "row": 0,
  "column": 0,
  "width": 12,
  "height": 1
}
```

- Grid is 12 columns wide
- `row` and `column` are 0-indexed
- Charts in the same row must not overlap (column + width <= 12)
- `height` is in grid units; taller charts give more visual space to the visualization

Typical sizes:
- Text/header panel: width=12, height=1
- Stat (SingleValue): width=3 or 4, height=1
- Time series (standard): width=6, height=1
- Time series (wide/important): width=12, height=1 or 2
- Heatmap: width=12, height=2
- List: width=6, height=2

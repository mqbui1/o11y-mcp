# o11y-mcp — Splunk Observability Cloud MCP Server

An [MCP (Model Context Protocol)](https://modelcontextprotocol.io) server that exposes the [Splunk Observability Cloud API](https://dev.splunk.com/observability/docs) as tools for Claude and other MCP-compatible AI assistants.

Ask Claude to investigate incidents, build dashboards, create detectors, query metrics, and analyze traces — all directly against your Splunk Observability environment.

---

## What you can do

- **Investigate incidents** — list active alerts, get detector details, clear resolved incidents
- **Query metrics** — search metrics, execute ad-hoc SignalFlow programs, browse MTS metadata
- **Analyze traces** — search traces, get full span waterfalls, find latency outliers, explore the service map
- **Build dashboards** — create charts and dashboards with SignalFlow-powered visualizations
- **Manage detectors** — create, update, delete detectors and muting rules
- **Explore your org** — teams, users, integrations, access tokens, dimensions

---

## Tools

| Category | Tools |
|---|---|
| **Detectors** | `list_detectors`, `get_detector`, `create_detector`, `update_detector`, `delete_detector`, `get_detector_incidents` |
| **Incidents** | `list_incidents`, `get_incident`, `clear_incident` |
| **Dashboards** | `list_dashboards`, `get_dashboard`, `create_dashboard`, `update_dashboard`, `delete_dashboard` |
| **Dashboard Groups** | `list_dashboard_groups`, `get_dashboard_group` |
| **Charts** | `create_chart`, `get_chart`, `update_chart`, `delete_chart`, `list_charts_in_dashboard` |
| **Metrics** | `search_metrics`, `get_metric_metadata`, `get_mts_summary` |
| **Metric Time Series** | `search_metric_time_series`, `get_mts_metadata` |
| **Dimensions** | `search_dimensions`, `get_dimension`, `update_dimension` |
| **SignalFlow** | `execute_signalflow`, `generate_signalflow_program` |
| **APM / Traces** | `search_traces`, `get_trace`, `get_trace_full`, `get_trace_analysis`, `get_trace_outliers`, `list_trace_services`, `search_trace_span_tags` |
| **Service Map** | `get_service_topology`, `get_service_dependencies`, `search_service_map`, `get_service_map_for_trace` |
| **Events** | `search_events`, `get_event`, `send_custom_event` |
| **Muting Rules** | `list_muting_rules`, `create_muting_rule`, `delete_muting_rule` |
| **Teams** | `list_teams`, `get_team`, `create_team` |
| **Org** | `get_organization`, `list_org_tokens`, `list_users`, `get_user`, `invite_user` |
| **Integrations** | `list_integrations`, `get_integration`, `delete_integration` |

---

## Requirements

- Python 3.10+
- [`uv`](https://github.com/astral-sh/uv) (recommended) or `pip`
- A Splunk Observability Cloud account with an API access token

---

## Setup

### 1. Get your credentials

- **Access Token**: Splunk Observability Cloud → Settings → Access Tokens → create or copy an org-level token
- **Realm**: Settings → Profile — shown as `us0`, `us1`, `eu0`, `ap0`, `ap1`, `au0`
- **Ingest Token** *(optional)*: Only needed for `send_custom_event`. Create a token with INGEST scope.

### 2. Configure Claude Desktop

Add to your `claude_desktop_config.json`:

**With `uv` (recommended — no install needed):**
```json
{
  "mcpServers": {
    "splunk-observability": {
      "command": "uv",
      "args": [
        "run",
        "--with", "mcp[cli]",
        "--script",
        "/absolute/path/to/o11y-mcp/o11y-mcp/server.py"
      ],
      "env": {
        "SPLUNK_ACCESS_TOKEN": "your-access-token",
        "SPLUNK_REALM": "us1"
      }
    }
  }
}
```

**With `pip`:**
```bash
pip install mcp
```
```json
{
  "mcpServers": {
    "splunk-observability": {
      "command": "python3",
      "args": ["/absolute/path/to/o11y-mcp/o11y-mcp/server.py"],
      "env": {
        "SPLUNK_ACCESS_TOKEN": "your-access-token",
        "SPLUNK_REALM": "us1"
      }
    }
  }
}
```

**Config file locations:**
| Platform | Path |
|---|---|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| Linux | `~/.config/Claude/claude_desktop_config.json` |

### 3. Restart Claude Desktop

After saving the config, restart Claude Desktop. The Splunk tools will appear in the tools panel.

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `SPLUNK_ACCESS_TOKEN` | Yes | — | Org-level API access token |
| `SPLUNK_REALM` | No | `us0` | Your Splunk realm (e.g. `us1`, `eu0`) |
| `SPLUNK_INGEST_TOKEN` | No | falls back to `SPLUNK_ACCESS_TOKEN` | Token with INGEST scope, for `send_custom_event` |

---

## Example prompts

```
List all my active detectors
```
```
Show me all firing incidents right now
```
```
Search for traces from the checkout-service in the last 30 minutes with errors
```
```
Execute a SignalFlow query: data('cpu.utilization').mean().publish()
```
```
Create a service health dashboard for api-gateway with golden signals
```
```
Mute alerts for host=web-01 for the next 2 hours
```
```
What's the P99 latency for the payments-service right now?
```
```
Show me the service map for environment=production
```
```
Find the slowest traces in the last hour and analyze what's causing the latency
```

---

## Skills (Claude Code)

The `skills/` directory contains [Claude Code skill files](https://docs.anthropic.com/en/docs/claude-code/skills) — structured guidance that tells Claude *how* to use the MCP tools effectively for common workflows. These are not part of the MCP server itself; they are loaded by Claude Code when you invoke them.

| Skill | What it does |
|---|---|
| `production-investigation` | Step-by-step incident triage: orient → characterize → localize → drill into traces → verify → resolve |
| `create-splunk-dashboard` | Design and build dashboards with golden signals, validated SignalFlow, and proper grid layout |
| `detectors-and-alerts` | Create and tune detectors with correct SignalFlow `detect()` programs and alert severity |
| `signalflow-queries` | Write and debug SignalFlow programs — syntax rules, filters, aggregations, common pitfalls |
| `apm-traces` | Search and interpret distributed traces, span tags, latency contributors, and the service map |

To use a skill in Claude Code, run `/production-investigation` or `/create-splunk-dashboard` etc.

---

## Project structure

```
o11y-mcp/
├── o11y-mcp/
│   ├── server.py                  # MCP server — all tools defined here
│   ├── requirements.txt           # mcp>=1.0.0
│   └── claude_desktop_config.json # Example config (tokens redacted)
└── skills/                        # Claude Code skills (not part of the server)
    ├── production-investigation/
    ├── create-splunk-dashboard/
    ├── detectors-and-alerts/
    ├── signalflow-queries/
    └── apm-traces/
```

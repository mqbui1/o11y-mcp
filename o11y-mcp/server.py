#!/usr/bin/env python3
"""
Splunk Observability Cloud MCP Server

Exposes Splunk Observability Cloud (formerly SignalFx) APIs as MCP tools.

Required env vars:
  SPLUNK_ACCESS_TOKEN  - Your Splunk Observability API access token
  SPLUNK_REALM         - Your realm (e.g. us0, us1, eu0, ap0) — defaults to us0
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

# ── Config ─────────────────────────────────────────────────────────────────────

ACCESS_TOKEN  = os.environ.get("SPLUNK_ACCESS_TOKEN")
# SPLUNK_INGEST_TOKEN is required for send_custom_event (ingest.{realm} endpoint).
# Falls back to ACCESS_TOKEN but will 401 if that token lacks INGEST scope.
INGEST_TOKEN  = os.environ.get("SPLUNK_INGEST_TOKEN") or ACCESS_TOKEN
REALM = os.environ.get("SPLUNK_REALM", "us0")

if not ACCESS_TOKEN:
    print("Error: SPLUNK_ACCESS_TOKEN environment variable is required.", file=sys.stderr)
    sys.exit(1)

BASE_URL   = f"https://api.{REALM}.signalfx.com"
APP_URL    = f"https://app.{REALM}.signalfx.com"
STREAM_URL = f"https://stream.{REALM}.signalfx.com"
INGEST_URL = f"https://ingest.{REALM}.signalfx.com"

# ── SignalFlow Sanitizer ───────────────────────────────────────────────────────

def _sanitize_signalflow(program: str) -> str:
    """
    Auto-fix the three most common SignalFlow mistakes before sending to the API.

    Fix 1 — detect() requires a boolean condition, not a raw stream.
      Bad:  detect(A).publish(...)
      Good: detect(when(A > 0)).publish(...)
      Bare stream variables are wrapped in when(...> 0) automatically.
      Already-correct forms like detect(when(...)) are not modified.

    Fix 2 — data() accepts only ONE filter via the named 'filter=' keyword.
      Bad:  data('metric', filter('k','v'), filter('k2','v2'))
      Good: data('metric', filter=filter('k','v') and filter('k2','v2'))
      Multiple positional filter() args cause a "unsupported type for argument
      rollup" API error because SignalFlow treats the second filter as the
      rollup positional arg. Lines already using filter= are not modified.

    Fix 3 — lasting= is a parameter of when(), not detect().
      Bad:  detect(when(A > B), lasting='5m')
      Good: detect(when(A > B, lasting='5m'))
      The lasting kwarg after the closing when() paren is moved inside when().
    """
    lines = program.splitlines()
    fixed_lines = []

    for line in lines:
        # Fix 1: detect(VARNAME) → detect(when(VARNAME > 0))
        # Matches a bare identifier inside detect() — not when(...), not A > 0
        line = re.sub(
            r'\bdetect\(\s*([A-Za-z_]\w*)\s*\)',
            lambda m: f'detect(when({m.group(1)} > 0))',
            line,
        )

        # Fix 3: detect(when(...), lasting='Xm') → detect(when(..., lasting='Xm'))
        # Moves a top-level lasting= kwarg on detect() inside the when() call.
        line = re.sub(
            r'\bdetect\((when\((.+?)\)),\s*(lasting\s*=\s*[\'"][^\'"]+[\'"])\)',
            lambda m: f'detect(when({m.group(2)}, {m.group(3)}))',
            line,
        )

        # Fix 2: data('metric', filter(...), filter(...)) → filter=f1 and f2
        # Only applied when there are 2+ positional filter() calls and no filter= present
        if re.search(r"\bdata\(", line) and "filter=" not in line:
            m = re.search(r'\bdata\((.+)\)', line)
            if m:
                inner = m.group(1)
                parts = _split_top_level(inner)
                filter_parts = []
                non_filter_parts = []
                for part in parts:
                    stripped = part.strip()
                    if re.match(r"filter\s*\(", stripped):
                        filter_parts.append(stripped)
                    else:
                        non_filter_parts.append(stripped)
                if len(filter_parts) >= 2:
                    combined = " and ".join(filter_parts)
                    new_inner = ", ".join(non_filter_parts + [f"filter={combined}"])
                    line = line[:m.start()] + f"data({new_inner})" + line[m.end():]

        fixed_lines.append(line)

    return "\n".join(fixed_lines)


def _split_top_level(s: str) -> list[str]:
    """Split string on commas that are not inside parentheses."""
    parts = []
    depth = 0
    current: list[str] = []
    for ch in s:
        if ch == '(':
            depth += 1
            current.append(ch)
        elif ch == ')':
            depth -= 1
            current.append(ch)
        elif ch == ',' and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current))
    return parts


# ── HTTP Helper ────────────────────────────────────────────────────────────────

def splunk_request(
    method: str,
    path: str,
    body: dict | list | None = None,
    base_url: str = BASE_URL,
    extra_headers: dict | None = None,
) -> Any:
    url = f"{base_url}{path}"
    token = INGEST_TOKEN if base_url == INGEST_URL else ACCESS_TOKEN
    headers = {
        "X-SF-Token": token,
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)

    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            detail = json.loads(raw)
        except Exception:
            detail = raw
        raise RuntimeError(f"Splunk API error {e.code}: {json.dumps(detail)}")


def qs(params: dict) -> str:
    """Build a query string, omitting None/False-ish values (but keeping 0)."""
    filtered = {k: str(v) for k, v in params.items() if v is not None}
    return ("?" + urllib.parse.urlencode(filtered)) if filtered else ""


# ── MCP Server ─────────────────────────────────────────────────────────────────

app = Server("splunk-observability-mcp")

# ── Tool Definitions ───────────────────────────────────────────────────────────

@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [

        # ════════════════════════════════════════════════════════════════════
        # DETECTORS
        # ════════════════════════════════════════════════════════════════════
        types.Tool(
            name="list_detectors",
            description="List all detectors in your Splunk Observability organization.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name":   {"type": "string",  "description": "Filter by name (partial match)"},
                    "limit":  {"type": "integer", "description": "Max results (default 50)"},
                    "offset": {"type": "integer", "description": "Pagination offset"},
                    "tags":   {"type": "string",  "description": "Comma-separated tags to filter by"},
                },
            },
        ),
        types.Tool(
            name="get_detector",
            description="Get details of a specific detector by ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "detector_id": {"type": "string"},
                },
                "required": ["detector_id"],
            },
        ),
        types.Tool(
            name="create_detector",
            description=(
                "Create a new detector with SignalFlow program text and alert rules.\n\n"
                "SignalFlow rules:\n"
                "  1. detect() requires a boolean condition — use detect(when(A > threshold))\n"
                "     NOT detect(A). A bare stream variable is not a valid condition.\n"
                "  2. data() accepts only one filter via the named 'filter=' keyword.\n"
                "     Combine multiple filters with 'and':\n"
                "       filter=filter('sf_service','svc') and filter('error','true')\n"
                "     NOT: data('metric', filter('k','v'), filter('k2','v2'))\n"
                "  3. filter() with multiple values is an OR across those values:\n"
                "       filter('sf_service', 'svc-a', 'svc-b', 'svc-c')\n\n"
                "Example program:\n"
                "  f = filter('sf_service', 'my-svc')\n"
                "  A = data('spans.count', filter=f).sum(by=['sf_environment']).mean(over='5m')\n"
                "  B = data('spans.count', filter=f).sum(by=['sf_environment']).mean(over='1h')\n"
                "  detect(when(A > B * 10)).publish('my-label')\n\n"
                "Note: common SignalFlow mistakes are auto-corrected by the server before\n"
                "submission (bare detect(A) and multiple positional filter() args)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name":            {"type": "string"},
                    "description":     {"type": "string"},
                    "signalFlowText":  {"type": "string", "description": "SignalFlow program text"},
                    "rules": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "severity":    {"type": "string", "enum": ["Critical","Major","Minor","Warning","Info"]},
                                "detectLabel": {"type": "string"},
                                "name":        {"type": "string"},
                                "description": {"type": "string"},
                                "disabled":    {"type": "boolean"},
                            },
                        },
                    },
                    "tags":           {"type": "array", "items": {"type": "string"}},
                    "teams":          {"type": "array", "items": {"type": "string"}},
                    "programOptions": {"type": "object"},
                },
                "required": ["name", "signalFlowText", "rules"],
            },
        ),
        types.Tool(
            name="update_detector",
            description="Update an existing detector.",
            inputSchema={
                "type": "object",
                "properties": {
                    "detector_id":    {"type": "string"},
                    "name":           {"type": "string"},
                    "description":    {"type": "string"},
                    "signalFlowText": {"type": "string"},
                    "rules":          {"type": "array", "items": {"type": "object"}},
                    "tags":           {"type": "array", "items": {"type": "string"}},
                },
                "required": ["detector_id"],
            },
        ),
        types.Tool(
            name="delete_detector",
            description="Delete a detector by ID.",
            inputSchema={
                "type": "object",
                "properties": {"detector_id": {"type": "string"}},
                "required": ["detector_id"],
            },
        ),
        types.Tool(
            name="get_detector_incidents",
            description="Get all active incidents for a specific detector.",
            inputSchema={
                "type": "object",
                "properties": {"detector_id": {"type": "string"}},
                "required": ["detector_id"],
            },
        ),

        # ════════════════════════════════════════════════════════════════════
        # INCIDENTS / ALERTS
        # ════════════════════════════════════════════════════════════════════
        types.Tool(
            name="list_incidents",
            description="List all active incidents/alerts across the organization.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit":           {"type": "integer"},
                    "offset":          {"type": "integer"},
                    "includeResolved": {"type": "boolean", "description": "Include resolved incidents"},
                },
            },
        ),
        types.Tool(
            name="get_incident",
            description="Get a specific incident by ID.",
            inputSchema={
                "type": "object",
                "properties": {"incident_id": {"type": "string"}},
                "required": ["incident_id"],
            },
        ),
        types.Tool(
            name="clear_incident",
            description="Manually clear (resolve) an active incident.",
            inputSchema={
                "type": "object",
                "properties": {"incident_id": {"type": "string"}},
                "required": ["incident_id"],
            },
        ),

        # ════════════════════════════════════════════════════════════════════
        # DASHBOARDS
        # ════════════════════════════════════════════════════════════════════
        types.Tool(
            name="list_dashboards",
            description="List dashboards in the organization.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name":   {"type": "string"},
                    "limit":  {"type": "integer"},
                    "offset": {"type": "integer"},
                    "tags":   {"type": "string"},
                },
            },
        ),
        types.Tool(
            name="get_dashboard",
            description="Get details of a specific dashboard.",
            inputSchema={
                "type": "object",
                "properties": {"dashboard_id": {"type": "string"}},
                "required": ["dashboard_id"],
            },
        ),
        types.Tool(
            name="create_dashboard",
            description="Create a new dashboard. Provide group_id to add it to an existing dashboard group (strongly recommended — Splunk requires a group). If group_id is omitted, a new group is auto-created with the same name.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name":        {"type": "string"},
                    "description": {"type": "string"},
                    "group_id":    {"type": "string", "description": "Dashboard group ID to add the dashboard to. Use list_dashboard_groups to find one."},
                    "charts":      {"type": "array", "items": {"type": "object"}},
                    "tags":        {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name"],
            },
        ),
        types.Tool(
            name="delete_dashboard",
            description="Delete a dashboard.",
            inputSchema={
                "type": "object",
                "properties": {"dashboard_id": {"type": "string"}},
                "required": ["dashboard_id"],
            },
        ),

        # ════════════════════════════════════════════════════════════════════
        # DASHBOARD GROUPS
        # ════════════════════════════════════════════════════════════════════
        types.Tool(
            name="list_dashboard_groups",
            description="List all dashboard groups.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name":   {"type": "string"},
                    "limit":  {"type": "integer"},
                    "offset": {"type": "integer"},
                },
            },
        ),
        types.Tool(
            name="get_dashboard_group",
            description="Get a dashboard group by ID.",
            inputSchema={
                "type": "object",
                "properties": {"group_id": {"type": "string"}},
                "required": ["group_id"],
            },
        ),

        # ════════════════════════════════════════════════════════════════════
        # CHARTS
        # ════════════════════════════════════════════════════════════════════
        types.Tool(
            name="create_chart",
            description="Create a new chart. Specify programText (SignalFlow) and options.type ('TimeSeriesChart', 'SingleValue', 'Heatmap', 'List', 'Event', 'Text'). Optionally include a groupId to add it to a dashboard group, or chartIds in a dashboard update.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name":        {"type": "string"},
                    "description": {"type": "string"},
                    "programText": {"type": "string", "description": "SignalFlow program text"},
                    "options":     {"type": "object", "description": "Chart visualization options, e.g. {\"type\": \"TimeSeriesChart\", \"defaultPlotType\": \"ColumnChart\", \"time\": {\"type\": \"relative\", \"range\": 86400000}}"},
                    "tags":        {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "programText"],
            },
        ),
        types.Tool(
            name="get_chart",
            description="Get details of a specific chart.",
            inputSchema={
                "type": "object",
                "properties": {"chart_id": {"type": "string"}},
                "required": ["chart_id"],
            },
        ),
        types.Tool(
            name="update_chart",
            description="Update an existing chart's name, description, programText, or options.",
            inputSchema={
                "type": "object",
                "properties": {
                    "chart_id":    {"type": "string"},
                    "name":        {"type": "string"},
                    "description": {"type": "string"},
                    "programText": {"type": "string", "description": "SignalFlow program text"},
                    "options":     {"type": "object", "description": "Chart visualization options"},
                    "tags":        {"type": "array", "items": {"type": "string"}},
                },
                "required": ["chart_id"],
            },
        ),
        types.Tool(
            name="delete_chart",
            description="Delete a chart by ID.",
            inputSchema={
                "type": "object",
                "properties": {"chart_id": {"type": "string"}},
                "required": ["chart_id"],
            },
        ),
        types.Tool(
            name="list_charts_in_dashboard",
            description="List all charts in a specific dashboard.",
            inputSchema={
                "type": "object",
                "properties": {"dashboard_id": {"type": "string"}},
                "required": ["dashboard_id"],
            },
        ),
        types.Tool(
            name="update_dashboard",
            description="Update an existing dashboard — add/remove charts, change name, description, or tags. Charts are specified as a list of {chartId, row, column, width, height} objects. groupId is fetched automatically from the existing dashboard.",
            inputSchema={
                "type": "object",
                "properties": {
                    "dashboard_id": {"type": "string"},
                    "name":         {"type": "string"},
                    "description":  {"type": "string"},
                    "charts":       {"type": "array", "items": {"type": "object"}, "description": "List of {chartId, row, column, width, height}"},
                    "tags":         {"type": "array", "items": {"type": "string"}},
                },
                "required": ["dashboard_id"],
            },
        ),

        # ════════════════════════════════════════════════════════════════════
        # METRICS / MTS
        # ════════════════════════════════════════════════════════════════════
        types.Tool(
            name="search_metrics",
            description="Search for metrics by name or pattern.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query":  {"type": "string", "description": "Metric name or search query (e.g. 'cpu.*')"},
                    "limit":  {"type": "integer"},
                    "offset": {"type": "integer"},
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="get_metric_metadata",
            description="Get metadata for a specific metric by name.",
            inputSchema={
                "type": "object",
                "properties": {
                    "metric_name": {"type": "string", "description": "e.g. 'cpu.utilization'"},
                },
                "required": ["metric_name"],
            },
        ),
        types.Tool(
            name="search_metric_time_series",
            description="Search for metric time series (MTS) matching a query.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query":  {"type": "string", "description": "e.g. 'sf_metric:cpu.utilization AND host:web-01'"},
                    "limit":  {"type": "integer"},
                    "offset": {"type": "integer"},
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="get_mts_metadata",
            description="Get metadata for a specific metric time series by TSID.",
            inputSchema={
                "type": "object",
                "properties": {"tsid": {"type": "string"}},
                "required": ["tsid"],
            },
        ),

        # ════════════════════════════════════════════════════════════════════
        # DIMENSIONS
        # ════════════════════════════════════════════════════════════════════
        types.Tool(
            name="search_dimensions",
            description="Search for dimension key-value pairs.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query":  {"type": "string", "description": "e.g. 'key:host AND value:web*'"},
                    "limit":  {"type": "integer"},
                    "offset": {"type": "integer"},
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="get_dimension",
            description="Get a specific dimension by key and value.",
            inputSchema={
                "type": "object",
                "properties": {
                    "key":   {"type": "string"},
                    "value": {"type": "string"},
                },
                "required": ["key", "value"],
            },
        ),
        types.Tool(
            name="update_dimension",
            description="Update custom properties or tags on a dimension.",
            inputSchema={
                "type": "object",
                "properties": {
                    "key":              {"type": "string"},
                    "value":            {"type": "string"},
                    "customProperties": {"type": "object"},
                    "tags":             {"type": "array", "items": {"type": "string"}},
                },
                "required": ["key", "value"],
            },
        ),

        # ════════════════════════════════════════════════════════════════════
        # TEAMS
        # ════════════════════════════════════════════════════════════════════
        types.Tool(
            name="list_teams",
            description="List all teams in the organization.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name":   {"type": "string"},
                    "limit":  {"type": "integer"},
                    "offset": {"type": "integer"},
                },
            },
        ),
        types.Tool(
            name="get_team",
            description="Get a team by ID.",
            inputSchema={
                "type": "object",
                "properties": {"team_id": {"type": "string"}},
                "required": ["team_id"],
            },
        ),
        types.Tool(
            name="create_team",
            description="Create a new team.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name":        {"type": "string"},
                    "description": {"type": "string"},
                    "members":     {"type": "array", "items": {"type": "string"}, "description": "User IDs"},
                },
                "required": ["name"],
            },
        ),

        # ════════════════════════════════════════════════════════════════════
        # MUTING RULES
        # ════════════════════════════════════════════════════════════════════
        types.Tool(
            name="list_muting_rules",
            description="List all alert muting rules.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit":          {"type": "integer"},
                    "offset":         {"type": "integer"},
                    "includeExpired": {"type": "boolean"},
                },
            },
        ),
        types.Tool(
            name="create_muting_rule",
            description="Create a new alert muting rule.",
            inputSchema={
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "filters": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "property":      {"type": "string"},
                                "propertyValue": {"type": "string"},
                                "NOT":           {"type": "boolean"},
                            },
                        },
                    },
                    "startTime": {"type": "integer", "description": "ms since epoch"},
                    "stopTime":  {"type": "integer", "description": "ms since epoch"},
                },
                "required": ["filters"],
            },
        ),
        types.Tool(
            name="delete_muting_rule",
            description="Delete a muting rule.",
            inputSchema={
                "type": "object",
                "properties": {"rule_id": {"type": "string"}},
                "required": ["rule_id"],
            },
        ),

        # ════════════════════════════════════════════════════════════════════
        # ORGANIZATION / TOKENS
        # ════════════════════════════════════════════════════════════════════
        types.Tool(
            name="get_organization",
            description="Get information about the current organization.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="list_org_tokens",
            description="List organization access tokens.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit":  {"type": "integer"},
                    "offset": {"type": "integer"},
                },
            },
        ),

        # ════════════════════════════════════════════════════════════════════
        # USERS
        # ════════════════════════════════════════════════════════════════════
        types.Tool(
            name="list_users",
            description="List all users in the organization.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit":  {"type": "integer"},
                    "offset": {"type": "integer"},
                },
            },
        ),
        types.Tool(
            name="get_user",
            description="Get details of a specific user by ID.",
            inputSchema={
                "type": "object",
                "properties": {"user_id": {"type": "string"}},
                "required": ["user_id"],
            },
        ),
        types.Tool(
            name="invite_user",
            description="Invite a new user to the organization.",
            inputSchema={
                "type": "object",
                "properties": {
                    "email":     {"type": "string"},
                    "firstName": {"type": "string"},
                    "lastName":  {"type": "string"},
                    "admin":     {"type": "boolean", "description": "Grant admin privileges"},
                },
                "required": ["email"],
            },
        ),

        # ════════════════════════════════════════════════════════════════════
        # INTEGRATIONS
        # ════════════════════════════════════════════════════════════════════
        types.Tool(
            name="list_integrations",
            description="List all integrations (notification integrations, data integrations, etc.).",
            inputSchema={
                "type": "object",
                "properties": {
                    "type":   {"type": "string", "description": "Filter by integration type (e.g. 'Slack', 'PagerDuty', 'Webhook')"},
                    "limit":  {"type": "integer"},
                    "offset": {"type": "integer"},
                },
            },
        ),
        types.Tool(
            name="get_integration",
            description="Get details of a specific integration by ID.",
            inputSchema={
                "type": "object",
                "properties": {"integration_id": {"type": "string"}},
                "required": ["integration_id"],
            },
        ),
        types.Tool(
            name="delete_integration",
            description="Delete an integration by ID.",
            inputSchema={
                "type": "object",
                "properties": {"integration_id": {"type": "string"}},
                "required": ["integration_id"],
            },
        ),

        # ════════════════════════════════════════════════════════════════════
        # EVENTS
        # ════════════════════════════════════════════════════════════════════
        types.Tool(
            name="search_events",
            description="Search for events by eventType and time range. query must be the exact eventType string (e.g. 'deployment.started', 'anomaly.detected').",
            inputSchema={
                "type": "object",
                "properties": {
                    "query":     {"type": "string",  "description": "eventType to search for (required). e.g. 'deployment.started'"},
                    "startTime": {"type": "integer", "description": "Start time in ms since epoch"},
                    "endTime":   {"type": "integer", "description": "End time in ms since epoch"},
                    "limit":     {"type": "integer", "description": "Max results (default 100)"},
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="get_event",
            description="Get a specific event by ID.",
            inputSchema={
                "type": "object",
                "properties": {"event_id": {"type": "string"}},
                "required": ["event_id"],
            },
        ),
        types.Tool(
            name="send_custom_event",
            description="Send a custom event to Splunk Observability Cloud.",
            inputSchema={
                "type": "object",
                "properties": {
                    "eventType":       {"type": "string",  "description": "Event type name"},
                    "category":        {"type": "string",  "description": "Event category: USER_DEFINED, ALERT, AUDIT, JOB, COLLECTD, SERVICE_DISCOVERY, EXCEPTION"},
                    "dimensions":      {"type": "object",  "description": "Key-value dimensions"},
                    "properties":      {"type": "object",  "description": "Key-value properties"},
                    "timestamp":       {"type": "integer", "description": "Event time in ms since epoch (defaults to now)"},
                },
                "required": ["eventType", "category"],
            },
        ),

        # ════════════════════════════════════════════════════════════════════
        # APM — SERVICE TOPOLOGY
        # ════════════════════════════════════════════════════════════════════
        types.Tool(
            name="get_service_topology",
            description=(
                "Retrieve the full APM service topology (service map) matching the given filters "
                "and time range. Returns up to 1,000 service nodes and their connections."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "timeRange": {
                        "type": "string",
                        "description": "ISO 8601 interval e.g. '2024-01-01T00:00:00Z/2024-01-02T00:00:00Z'",
                    },
                    "tagFilters": {
                        "type": "array",
                        "description": "Tag filters to narrow results",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name":     {"type": "string", "description": "e.g. 'sf_environment'"},
                                "operator": {"type": "string", "description": "e.g. 'equals'"},
                                "value":    {"type": "string", "description": "e.g. 'production'"},
                            },
                        },
                    },
                },
                "required": ["timeRange"],
            },
        ),
        types.Tool(
            name="get_service_dependencies",
            description=(
                "Retrieve direct inbound and outbound dependencies for a specific APM service. "
                "Does not include transitive dependencies."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "serviceName": {"type": "string", "description": "Name of the service"},
                    "timeRange": {
                        "type": "string",
                        "description": "ISO 8601 interval e.g. '2024-01-01T00:00:00Z/2024-01-02T00:00:00Z'",
                    },
                    "tagFilters": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name":     {"type": "string"},
                                "operator": {"type": "string"},
                                "value":    {"type": "string"},
                            },
                        },
                    },
                },
                "required": ["serviceName", "timeRange"],
            },
        ),

        # ════════════════════════════════════════════════════════════════════
        # APM — TRACES
        # ════════════════════════════════════════════════════════════════════
        types.Tool(
            name="get_trace",
            description=(
                "Retrieve all spans for a specific trace by its trace ID. "
                "Returns the full trace with all spans as an array."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "trace_id": {
                        "type": "string",
                        "description": "The trace ID (hex string)",
                    },
                },
                "required": ["trace_id"],
            },
        ),
        types.Tool(
            name="search_traces",
            description=(
                "Search for APM traces by service, operation, tags, and time range. "
                "Returns matching traces with their top-level metadata."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "environment": {
                        "type": "string",
                        "description": "APM environment to search (e.g. 'mcp-68e4-workshop'). Strongly recommended — searches without an environment filter may fail.",
                    },
                    "services": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by service names",
                    },
                    "operations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by operation/span names",
                    },
                    "tags": {
                        "type": "object",
                        "description": "Key-value span tags to filter by (e.g. {\"http.status_code\": \"500\"})",
                    },
                    "startTimeMs": {
                        "type": "integer",
                        "description": "Start of search window in ms since epoch",
                    },
                    "endTimeMs": {
                        "type": "integer",
                        "description": "End of search window in ms since epoch",
                    },
                    "minDurationMs": {
                        "type": "integer",
                        "description": "Only return traces longer than this duration (ms). Note: not enforced server-side, filter client-side.",
                    },
                    "maxDurationMs": {
                        "type": "integer",
                        "description": "Only return traces shorter than this duration (ms)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of traces to return (default 20)",
                    },
                },
            },
        ),
        types.Tool(
            name="get_trace_full",
            description=(
                "Retrieve full span details for a trace using the GraphQL endpoint. "
                "Returns all spans with operation names, service names, durations, tags, and logs."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "trace_id": {"type": "string", "description": "The trace ID (hex string)"},
                    "startTimeMs": {"type": "integer", "description": "Start of search window in ms since epoch"},
                    "endTimeMs": {"type": "integer", "description": "End of search window in ms since epoch"},
                },
                "required": ["trace_id"],
            },
        ),
        types.Tool(
            name="get_trace_analysis",
            description=(
                "Get anomaly analysis for a specific trace, including top latency contributors, "
                "repeated serial spans, parent-child delays, and clock skew."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "trace_id": {"type": "string", "description": "The trace ID (hex string)"},
                },
                "required": ["trace_id"],
            },
        ),
        types.Tool(
            name="search_trace_span_tags",
            description=(
                "Retrieve span tags available for traces matching the given search criteria. "
                "Useful for discovering filterable attributes on your traces."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "services": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by service names",
                    },
                    "operations": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "startTimeMs": {"type": "integer"},
                    "endTimeMs":   {"type": "integer"},
                    "tags":        {"type": "object", "description": "Existing tag filters"},
                },
            },
        ),
        types.Tool(
            name="list_trace_services",
            description=(
                "List all services that have reported traces in the last 48 hours, "
                "along with their available operations/endpoints."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "services": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter to specific services",
                    },
                },
            },
        ),
        types.Tool(
            name="get_trace_outliers",
            description=(
                "Find traces that are the biggest contributors to latency "
                "(outlier traces). Useful for identifying performance bottlenecks."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "services": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Services to search within",
                    },
                    "operations": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "startTimeMs": {"type": "integer"},
                    "endTimeMs":   {"type": "integer"},
                    "tags":        {"type": "object"},
                    "limit":       {"type": "integer"},
                },
            },
        ),
        types.Tool(
            name="get_service_map_for_trace",
            description=(
                "Retrieve the service map (dependencies) specifically for a single trace, "
                "identified by its trace ID."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "trace_id": {"type": "string"},
                },
                "required": ["trace_id"],
            },
        ),
        types.Tool(
            name="search_service_map",
            description=(
                "Retrieve the service map for traces matching the given search filters. "
                "Shows how services interact within the matched traces."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "services":    {"type": "array", "items": {"type": "string"}},
                    "operations":  {"type": "array", "items": {"type": "string"}},
                    "startTimeMs": {"type": "integer"},
                    "endTimeMs":   {"type": "integer"},
                    "tags":        {"type": "object"},
                },
            },
        ),

        # ════════════════════════════════════════════════════════════════════
        # SIGNALFLOW
        # ════════════════════════════════════════════════════════════════════
        types.Tool(
            name="execute_signalflow",
            description=(
                "Execute a SignalFlow program and get results. "
                "Use for ad-hoc metric queries and analytics. "
                "Example: data('cpu.utilization').mean().publish()"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "program":    {"type": "string",  "description": "SignalFlow program text"},
                    "start":      {"type": "integer", "description": "Start time ms since epoch (default: -1h)"},
                    "stop":       {"type": "integer", "description": "Stop time ms since epoch (default: now)"},
                    "resolution": {"type": "integer", "description": "Resolution in ms"},
                    "maxDelay":   {"type": "integer", "description": "Max delay in ms"},
                    "immediate":  {"type": "boolean", "description": "Return only data up to current time"},
                },
                "required": ["program"],
            },
        ),
    ]


# ── Tool Handlers ──────────────────────────────────────────────────────────────

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        result = handle_tool(name, arguments)
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    except Exception as e:
        return [types.TextContent(type="text", text=f"Error: {e}")]


def handle_tool(name: str, args: dict) -> Any:  # noqa: C901
    match name:

        # ── Detectors ─────────────────────────────────────────────────────────
        case "list_detectors":
            return splunk_request("GET", "/v2/detector" + qs({
                "name": args.get("name"), "limit": args.get("limit"),
                "offset": args.get("offset"), "tags": args.get("tags"),
            }))
        case "get_detector":
            return splunk_request("GET", f"/v2/detector/{args['detector_id']}")

        case "create_detector":
            # "signalFlowText" is the MCP-facing param name; Splunk API requires "programText".
            # _sanitize_signalflow() auto-fixes bare detect(A) and multiple positional filters.
            raw_program = args.get("signalFlowText", "")
            body = {}
            if args.get("name"):
                body["name"] = args["name"]
            if args.get("description"):
                body["description"] = args["description"]
            if raw_program:
                body["programText"] = _sanitize_signalflow(raw_program)  # ← remap + sanitize
            if args.get("rules"):
                body["rules"] = args["rules"]
            if args.get("tags"):
                body["tags"] = args["tags"]
            if args.get("teams"):
                body["teams"] = args["teams"]
            if args.get("programOptions"):
                body["programOptions"] = args["programOptions"]
            return splunk_request("POST", "/v2/detector", body)

        case "update_detector":
            detector_id = args["detector_id"]
            raw_program = args.get("signalFlowText", "")
            body = {}
            if args.get("name"):
                body["name"] = args["name"]
            if args.get("description"):
                body["description"] = args["description"]
            if raw_program:
                body["programText"] = _sanitize_signalflow(raw_program)  # ← remap + sanitize
            if args.get("rules"):
                body["rules"] = args["rules"]
            if args.get("tags"):
                body["tags"] = args["tags"]
            return splunk_request("PUT", f"/v2/detector/{detector_id}", body)

        case "delete_detector":
            return splunk_request("DELETE", f"/v2/detector/{args['detector_id']}")
        case "get_detector_incidents":
            return splunk_request("GET", f"/v2/detector/{args['detector_id']}/incidents")

        # ── Incidents ─────────────────────────────────────────────────────────
        case "list_incidents":
            return splunk_request("GET", "/v2/incident" + qs({
                "limit": args.get("limit"), "offset": args.get("offset"),
                "includeResolved": str(args["includeResolved"]).lower() if "includeResolved" in args else None,
            }))
        case "get_incident":
            return splunk_request("GET", f"/v2/incident/{args['incident_id']}")
        case "clear_incident":
            return splunk_request("PUT", f"/v2/incident/{args['incident_id']}/clear")

        # ── Dashboards ────────────────────────────────────────────────────────
        case "list_dashboards":
            return splunk_request("GET", "/v2/dashboard" + qs({
                "name": args.get("name"), "limit": args.get("limit"),
                "offset": args.get("offset"), "tags": args.get("tags"),
            }))
        case "get_dashboard":
            return splunk_request("GET", f"/v2/dashboard/{args['dashboard_id']}")
        case "create_dashboard":
            group_id = args.get("group_id")
            if not group_id:
                # Splunk requires a groupId — auto-create a group with the same name
                grp = splunk_request("POST", "/v2/dashboardgroup", {"name": args["name"]})
                group_id = grp.get("id")
            body = {k: v for k, v in {
                "name": args.get("name"), "description": args.get("description"),
                "groupId": group_id,
                "charts": args.get("charts", []), "tags": args.get("tags"),
            }.items() if v is not None}
            return splunk_request("POST", "/v2/dashboard", body)
        case "delete_dashboard":
            return splunk_request("DELETE", f"/v2/dashboard/{args['dashboard_id']}")

        # ── Dashboard Groups ──────────────────────────────────────────────────
        case "list_dashboard_groups":
            return splunk_request("GET", "/v2/dashboardgroup" + qs({
                "name": args.get("name"), "limit": args.get("limit"),
                "offset": args.get("offset"),
            }))
        case "get_dashboard_group":
            return splunk_request("GET", f"/v2/dashboardgroup/{args['group_id']}")

        # ── Charts ────────────────────────────────────────────────────────────
        case "create_chart":
            body = {k: v for k, v in {
                "name": args["name"], "description": args.get("description"),
                "programText": args["programText"], "options": args.get("options"),
                "tags": args.get("tags"),
            }.items() if v is not None}
            return splunk_request("POST", "/v2/chart", body)
        case "get_chart":
            return splunk_request("GET", f"/v2/chart/{args['chart_id']}")
        case "update_chart":
            body = {k: v for k, v in {
                "name": args.get("name"), "description": args.get("description"),
                "programText": args.get("programText"), "options": args.get("options"),
                "tags": args.get("tags"),
            }.items() if v is not None}
            return splunk_request("PUT", f"/v2/chart/{args['chart_id']}", body)
        case "delete_chart":
            return splunk_request("DELETE", f"/v2/chart/{args['chart_id']}")
        case "list_charts_in_dashboard":
            # The /v2/dashboard/{id}/chart endpoint doesn't exist — fetch the
            # dashboard and return its charts array instead.
            dash = splunk_request("GET", f"/v2/dashboard/{args['dashboard_id']}")
            return {"charts": dash.get("charts", []), "dashboard_id": args["dashboard_id"]}
        case "update_dashboard":
            # PUT requires groupId — fetch it from the existing dashboard first.
            existing = splunk_request("GET", f"/v2/dashboard/{args['dashboard_id']}")
            body = {"groupId": existing["groupId"]}
            for k in ("name", "description", "charts", "tags"):
                if args.get(k) is not None:
                    body[k] = args[k]
            # Preserve existing values for fields not being updated
            for k in ("name", "description", "charts", "tags"):
                if k not in body:
                    body[k] = existing.get(k)
            return splunk_request("PUT", f"/v2/dashboard/{args['dashboard_id']}", body)

        # ── Metrics ───────────────────────────────────────────────────────────
        case "search_metrics":
            q = args["query"]
            # API requires Lucene field:value syntax — bare names like "cpu" fail with 400.
            # Auto-prefix with sf_metric: if no field qualifier is present.
            if ":" not in q:
                q = f"sf_metric:{q}*"
            return splunk_request("GET", "/v2/metric" + qs({
                "query": q, "limit": args.get("limit"), "offset": args.get("offset"),
            }))
        case "get_metric_metadata":
            return splunk_request("GET", f"/v2/metric/{urllib.parse.quote(args['metric_name'], safe='')}")
        case "search_metric_time_series":
            return splunk_request("GET", "/v2/metrictimeseries" + qs({
                "query": args["query"], "limit": args.get("limit"), "offset": args.get("offset"),
            }))
        case "get_mts_metadata":
            return splunk_request("GET", f"/v2/metrictimeseries/{args['tsid']}")

        # ── Dimensions ────────────────────────────────────────────────────────
        case "search_dimensions":
            return splunk_request("GET", "/v2/dimension" + qs({
                "query": args["query"], "limit": args.get("limit"), "offset": args.get("offset"),
            }))
        case "get_dimension":
            return splunk_request("GET", f"/v2/dimension/{args['key']}/{args['value']}")
        case "update_dimension":
            return splunk_request("PUT", f"/v2/dimension/{args['key']}/{args['value']}", {
                k: v for k, v in {
                    "customProperties": args.get("customProperties"),
                    "tags": args.get("tags"),
                }.items() if v is not None
            })

        # ── Teams ─────────────────────────────────────────────────────────────
        case "list_teams":
            return splunk_request("GET", "/v2/team" + qs({
                "name": args.get("name"), "limit": args.get("limit"), "offset": args.get("offset"),
            }))
        case "get_team":
            return splunk_request("GET", f"/v2/team/{args['team_id']}")
        case "create_team":
            return splunk_request("POST", "/v2/team", {k: v for k, v in {
                "name": args["name"], "description": args.get("description"),
                "members": args.get("members", []),
            }.items() if v is not None})

        # ── Muting Rules ──────────────────────────────────────────────────────
        case "list_muting_rules":
            return splunk_request("GET", "/v2/alertmuting" + qs({
                "limit": args.get("limit"), "offset": args.get("offset"),
                "includeExpired": str(args["includeExpired"]).lower() if "includeExpired" in args else None,
            }))
        case "create_muting_rule":
            return splunk_request("POST", "/v2/alertmuting", {k: v for k, v in {
                "description": args.get("description"), "filters": args["filters"],
                "startTime": args.get("startTime"), "stopTime": args.get("stopTime"),
            }.items() if v is not None})
        case "delete_muting_rule":
            return splunk_request("DELETE", f"/v2/alertmuting/{args['rule_id']}")

        # ── Organization ──────────────────────────────────────────────────────
        case "get_organization":
            return splunk_request("GET", "/v2/organization")
        case "list_org_tokens":
            return splunk_request("GET", "/v2/token" + qs({
                "limit": args.get("limit"), "offset": args.get("offset"),
            }))

        # ── Users ─────────────────────────────────────────────────────────────
        case "list_users":
            return splunk_request("GET", "/v2/organization/member" + qs({
                "limit": args.get("limit"), "offset": args.get("offset"),
            }))
        case "get_user":
            return splunk_request("GET", f"/v2/organization/member/{args['user_id']}")
        case "invite_user":
            return splunk_request("POST", "/v2/organization/member", {k: v for k, v in {
                "email":     args["email"],
                "firstName": args.get("firstName"),
                "lastName":  args.get("lastName"),
                "admin":     args.get("admin"),
            }.items() if v is not None})

        # ── Integrations ──────────────────────────────────────────────────────
        case "list_integrations":
            return splunk_request("GET", "/v2/integration" + qs({
                "type": args.get("type"), "limit": args.get("limit"), "offset": args.get("offset"),
            }))
        case "get_integration":
            return splunk_request("GET", f"/v2/integration/{args['integration_id']}")
        case "delete_integration":
            return splunk_request("DELETE", f"/v2/integration/{args['integration_id']}")

        # ── Events ────────────────────────────────────────────────────────────
        case "search_events":
            # /v2/event GET returns 404 — use SignalFlow events() instead.
            # events() requires eventType — query must be provided.
            now_ms = int(time.time() * 1000)
            start_ms = args.get("startTime", now_ms - 3_600_000)
            stop_ms  = args.get("endTime",   now_ms)
            limit    = args.get("limit", 100)
            q        = args.get("query", "")
            if not q:
                return {"count": 0, "results": [], "note": "query (eventType) is required for search_events. Example: query='deployment.started'"}
            program = f"events(eventType='{q}').publish()"
            query_params = {"start": start_ms, "stop": stop_ms, "immediate": "true"}
            url = f"{STREAM_URL}/v2/signalflow/execute" + qs(query_params)
            headers = {"X-SF-Token": ACCESS_TOKEN, "Content-Type": "text/plain"}
            req = urllib.request.Request(url, data=program.encode(), headers=headers, method="POST")
            event_results = []
            try:
                with urllib.request.urlopen(req) as resp:
                    raw_body = resp.read().decode("utf-8")
                for chunk in raw_body.strip().split("\n\n"):
                    lines = [l[5:] for l in chunk.splitlines() if l.startswith("data:")]
                    payload = "".join(lines).strip()
                    if not payload:
                        continue
                    try:
                        msg = json.loads(payload)
                        if msg.get("type") == "event":
                            event_results.append(msg)
                    except json.JSONDecodeError:
                        pass
            except urllib.error.HTTPError as e:
                raise RuntimeError(f"Splunk API error {e.code}: {e.read().decode()}")
            return {"count": len(event_results[:limit]), "results": event_results[:limit]}
        case "get_event":
            return {"error": "get_event is not supported: Splunk Observability has no REST GET /v2/event/{id} endpoint. Use search_events with the eventType as query, or execute_signalflow with events(eventType='...').publish()."}
        case "send_custom_event":
            event = {k: v for k, v in {
                "eventType":  args["eventType"],
                "category":   args["category"],
                "dimensions": args.get("dimensions", {}),
                "properties": args.get("properties", {}),
                "timestamp":  args.get("timestamp", int(time.time() * 1000)),
            }.items() if v is not None}
            # ingest.{realm} requires array body and an ingest-scoped token
            return splunk_request("POST", "/v2/event", [event], base_url=INGEST_URL)

        # ── APM Service Topology ──────────────────────────────────────────────
        case "get_service_topology":
            body = {"timeRange": args["timeRange"]}
            if args.get("tagFilters"):
                body["tagFilters"] = [
                    {**f, "scope": f.get("scope", "global")} for f in args["tagFilters"]
                ]
            return splunk_request("POST", "/v2/apm/topology", body)

        case "get_service_dependencies":
            service = urllib.parse.quote(args["serviceName"], safe="")
            body = {"timeRange": args["timeRange"]}
            if args.get("tagFilters"):
                body["tagFilters"] = [
                    {**f, "scope": f.get("scope", "global")} for f in args["tagFilters"]
                ]
            return splunk_request("POST", f"/v2/apm/topology/{service}", body)

        # ── APM Traces ────────────────────────────────────────────────────────
        case "get_trace":
            trace_id = args["trace_id"]
            now_ms = int(time.time() * 1000)
            start_ms = args.get("startTimeMs", now_ms - 3_600_000)
            end_ms = args.get("endTimeMs", now_ms)
            return splunk_request(
                "GET",
                "/v2/apm/profiling/v2/traceSnapshotSummaries" + qs({
                    "traceId": trace_id,
                    "from": start_ms,
                    "to": end_ms,
                }),
                base_url=APP_URL,
            )

        case "get_trace_full":
            trace_id = args["trace_id"]
            query = (
                "query TraceFullDetailsLessValidation($id: ID!) {"
                " trace(id: $id) {"
                " traceID startTime duration"
                " spans { spanID operationName serviceName"
                " startTime duration tags { key value } } } }"
            )
            gql_body = {
                "operationName": "TraceFullDetailsLessValidation",
                "variables": {"id": trace_id},
                "query": query,
            }
            return splunk_request(
                "POST",
                "/v2/apm/graphql?op=TraceFullDetailsLessValidation",
                gql_body,
                base_url=APP_URL,
            )

        case "get_trace_analysis":
            trace_id = args["trace_id"]
            # Note: TraceSpan does NOT have a parentSpanID field — omitted.
            query = (
                "query TraceAnalysis($id: ID!) {"
                " trace(id: $id) {"
                " traceID startTime duration"
                " spans {"
                "   spanID operationName serviceName"
                "   startTime duration"
                "   tags { key value }"
                " } } }"
            )
            gql_body = {
                "operationName": "TraceAnalysis",
                "variables": {"id": trace_id},
                "query": query,
            }
            result = splunk_request(
                "POST",
                "/v2/apm/graphql?op=TraceAnalysis",
                gql_body,
                base_url=APP_URL,
            )
            spans = (result.get("data", {}).get("trace") or {}).get("spans", [])
            if not spans:
                return result
            sorted_by_duration = sorted(spans, key=lambda s: s.get("duration", 0), reverse=True)
            total_duration = sum(s.get("duration", 0) for s in spans)
            analysis = {
                "traceID": trace_id,
                "totalDuration": result.get("data", {}).get("trace", {}).get("duration"),
                "spanCount": len(spans),
                "topLatencyContributors": [
                    {
                        "spanID": s["spanID"],
                        "operationName": s.get("operationName"),
                        "serviceName": s.get("serviceName"),
                        "duration": s.get("duration"),
                        "percentOfTrace": round(s.get("duration", 0) / total_duration * 100, 1) if total_duration else 0,
                    }
                    for s in sorted_by_duration[:5]
                ],
                "rawTrace": result,
            }
            return analysis

        case "search_traces":
            now_ms = int(time.time() * 1000)
            start_ms = args.get("startTimeMs", now_ms - 3_600_000)
            end_ms = args.get("endTimeMs", now_ms)
            limit = args.get("limit", 50)

            trace_filters = []
            tag_filters = []
            if args.get("environment"):
                tag_filters.append({
                    "tag": "sf_environment", "operation": "IN",
                    "values": [args["environment"]],
                })
            if args.get("services"):
                tag_filters.append({
                    "tag": "sf_service", "operation": "IN",
                    "values": args["services"],
                })
            if args.get("operations"):
                tag_filters.append({
                    "tag": "sf_operation", "operation": "IN",
                    "values": args["operations"],
                })
            if args.get("tags"):
                for k, v in args["tags"].items():
                    tag_filters.append({
                        "tag": k, "operation": "IN",
                        "values": [v] if isinstance(v, str) else v,
                    })
            if tag_filters:
                trace_filters.append({
                    "traceFilter": {"tags": tag_filters},
                    "filterType": "traceFilter",
                })

            # Note: minDurationMs/maxDurationMs are not supported as filter
            # types by the trace analytics API (durationFilter is not a valid
            # filterType). These parameters are accepted but ignored to avoid
            # breaking callers — filter by duration client-side if needed.

            parameters = {
                "sharedParameters": {
                    "timeRangeMillis": {"gte": start_ms, "lte": end_ms},
                    "filters": trace_filters,
                    "samplingFactor": 100,
                },
                "sectionsParameters": [
                    {"sectionType": "traceExamples", "limit": limit},
                ],
            }

            start_body = {
                "operationName": "StartAnalyticsSearch",
                "variables": {"parameters": parameters},
                "query": (
                    "query StartAnalyticsSearch($parameters: JSON!) {\n"
                    "  startAnalyticsSearch(parameters: $parameters)\n"
                    "}\n"
                ),
            }
            start_result = splunk_request(
                "POST", "/v2/apm/graphql?op=StartAnalyticsSearch",
                start_body, base_url=APP_URL,
            )
            job_id = (
                (start_result.get("data") or {})
                .get("startAnalyticsSearch") or {}
            ).get("jobId")
            if not job_id:
                return {"error": "StartAnalyticsSearch did not return a jobId", "raw": start_result}

            get_body = {
                "operationName": "GetAnalyticsSearch",
                "variables": {"jobId": job_id},
                "query": (
                    "query GetAnalyticsSearch($jobId: ID!) {\n"
                    "  getAnalyticsSearch(jobId: $jobId)\n"
                    "}\n"
                ),
            }
            examples = []
            for _ in range(10):
                poll_result = splunk_request(
                    "POST", "/v2/apm/graphql?op=GetAnalyticsSearch",
                    get_body, base_url=APP_URL,
                )
                sections = (
                    (poll_result.get("data") or {})
                    .get("getAnalyticsSearch") or {}
                ).get("sections", [])
                for section in sections:
                    if section.get("sectionType") == "traceExamples":
                        examples = section.get("legacyTraceExamples") or []
                        if section.get("isComplete"):
                            return {
                                "traces": examples[:limit],
                                "traceCount": len(examples),
                                "jobId": job_id,
                                "isComplete": True,
                            }
                time.sleep(0.5)

            return {
                "traces": examples[:limit],
                "traceCount": len(examples),
                "jobId": job_id,
                "isComplete": False,
                "note": "Search job did not complete within poll limit. Partial results returned.",
            }

        case "search_trace_span_tags":
            query_parts = []
            if args.get("services"):
                svc_filter = " OR ".join(f"sf_service:{s}" for s in args["services"])
                query_parts.append(f"({svc_filter})")
            query = " AND ".join(query_parts) if query_parts else "sf_key:*"
            return splunk_request("GET", "/v2/dimension" + qs({
                "query": query,
                "limit": args.get("limit", 100),
                "offset": args.get("offset", 0),
            }))

        case "list_trace_services":
            now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            two_days_ago = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 172_800))
            body: dict = {"timeRange": f"{two_days_ago}/{now}"}
            if args.get("services"):
                body["tagFilters"] = [
                    {"name": "sf_service", "operator": "equals", "value": s, "scope": "global"}
                    for s in args["services"]
                ]
            result = splunk_request("POST", "/v2/apm/topology", body)
            nodes = (result.get("data") or {}).get("nodes", [])
            return {
                "services": [
                    {"serviceName": n["serviceName"], "inferred": n.get("inferred", False)}
                    for n in nodes
                ],
                "count": len(nodes),
            }

        case "get_trace_outliers":
            now_ms = int(time.time() * 1000)
            start_ms = args.get("startTimeMs", now_ms - 3_600_000)
            end_ms = args.get("endTimeMs", now_ms)
            limit = args.get("limit", 10)

            svc_filter = ""
            if args.get("services"):
                svc_filter = f", filter=filter('sf_service', '{args['services'][0]}')"
            if args.get("operations"):
                op = args["operations"][0]
                svc_filter += f".filter(filter('sf_operation', '{op}'))"

            program = (
                f"data('service.request.duration.ns.p99'{svc_filter})"
                f".publish(label='p99_latency')"
            )

            query_params = {
                "start":     start_ms,
                "stop":      end_ms,
                "immediate": "true",
            }
            url = f"{STREAM_URL}/v2/signalflow/execute" + qs(query_params)
            headers = {"X-SF-Token": ACCESS_TOKEN, "Content-Type": "text/plain"}
            req = urllib.request.Request(url, data=program.encode(), headers=headers, method="POST")

            data_points = []
            metadata = {}
            try:
                with urllib.request.urlopen(req) as resp:
                    raw_body = resp.read().decode("utf-8")
                events = raw_body.strip().split("\n\n")
                for event in events:
                    lines = [l[5:] if l.startswith("data:") else l
                             for l in event.splitlines()
                             if l.startswith("data:")]
                    payload = "".join(lines).strip()
                    if not payload:
                        continue
                    try:
                        msg = json.loads(payload)
                        if msg.get("type") == "data":
                            for pt in msg.get("data", []):
                                if pt.get("value") is not None:
                                    data_points.append({
                                        "tsId": pt.get("tsId"),
                                        "value": pt.get("value"),
                                        "timestampMs": msg.get("logicalTimestampMs"),
                                    })
                        elif msg.get("type") == "metadata":
                            metadata[msg.get("tsId")] = msg.get("properties", {})
                    except json.JSONDecodeError:
                        pass
            except urllib.error.HTTPError as e:
                raise RuntimeError(f"Splunk API error {e.code}: {e.read().decode()}")

            data_points.sort(key=lambda x: x.get("value", 0), reverse=True)
            outliers = []
            for pt in data_points[:limit]:
                meta = metadata.get(pt["tsId"], {})
                outliers.append({
                    "timestampMs":   pt["timestampMs"],
                    "p99LatencyNs":  pt["value"],
                    "p99LatencyMs":  round(pt["value"] / 1_000_000, 2) if pt["value"] else None,
                    "service":       meta.get("sf_service"),
                    "operation":     meta.get("sf_operation"),
                    "environment":   meta.get("sf_environment"),
                })

            return {
                "outliers": outliers,
                "count": len(outliers),
                "metric": "service.request.duration.ns.p99",
                "note": "Outlier windows by p99 latency. Use get_trace_full with a known trace ID to inspect individual traces.",
            }

        case "get_service_map_for_trace":
            trace_id = args["trace_id"]
            # Note: TraceSpan does NOT have a parentSpanID field.
            # Infer parent-child edges by timing containment instead.
            query = (
                "query TraceServiceMap($id: ID!) {"
                " trace(id: $id) {"
                " traceID"
                " spans { spanID operationName serviceName startTime duration } } }"
            )
            gql_body = {
                "operationName": "TraceServiceMap",
                "variables": {"id": trace_id},
                "query": query,
            }
            result = splunk_request(
                "POST",
                "/v2/apm/graphql?op=TraceServiceMap",
                gql_body,
                base_url=APP_URL,
            )
            spans = (result.get("data", {}).get("trace") or {}).get("spans", [])
            # Infer edges: span A is parent of span B if B's window is contained within A's
            # and A has the shortest duration among all containing spans (immediate parent).
            edges = set()
            for i, child in enumerate(spans):
                c_start = child.get("startTime", 0)
                c_end   = c_start + child.get("duration", 0)
                best_parent = None
                best_dur    = float("inf")
                for j, candidate in enumerate(spans):
                    if i == j:
                        continue
                    p_start = candidate.get("startTime", 0)
                    p_end   = p_start + candidate.get("duration", 0)
                    if p_start <= c_start and p_end >= c_end and candidate.get("duration", 0) < best_dur:
                        best_parent = candidate
                        best_dur    = candidate.get("duration", 0)
                if best_parent:
                    p_svc = best_parent.get("serviceName")
                    c_svc = child.get("serviceName")
                    if p_svc and c_svc and p_svc != c_svc:
                        edges.add((p_svc, c_svc))
            services = list({s.get("serviceName") for s in spans if s.get("serviceName")})
            return {
                "traceID": trace_id,
                "nodes": [{"serviceName": svc} for svc in services],
                "edges": [{"fromNode": e[0], "toNode": e[1]} for e in edges],
            }

        case "search_service_map":
            now_ms = int(time.time() * 1000)
            start_ms = args.get("startTimeMs", now_ms - 3_600_000)
            end_ms = args.get("endTimeMs", now_ms)
            start_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(start_ms / 1000))
            end_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(end_ms / 1000))
            body = {"timeRange": f"{start_iso}/{end_iso}"}
            if args.get("services"):
                body["tagFilters"] = [
                    {"name": "sf_service", "operator": "equals", "value": s, "scope": "global"}
                    for s in args["services"]
                ]
            return splunk_request("POST", "/v2/apm/topology", body)

        # ── SignalFlow ────────────────────────────────────────────────────────
        case "execute_signalflow":
            now_ms = int(time.time() * 1000)
            query_params = {k: v for k, v in {
                "start":      args.get("start", now_ms - 3_600_000),
                "stop":       args.get("stop", now_ms),
                "resolution": args.get("resolution"),
                "maxDelay":   args.get("maxDelay"),
                "immediate":  str(args.get("immediate", True)).lower(),
            }.items() if v is not None}
            url = f"{STREAM_URL}/v2/signalflow/execute" + qs(query_params)
            headers = {
                "X-SF-Token": ACCESS_TOKEN,
                "Content-Type": "text/plain",
            }
            encoded = args["program"].encode("utf-8")
            req = urllib.request.Request(url, data=encoded, headers=headers, method="POST")
            messages = []
            data_points = []
            metadata = {}
            try:
                with urllib.request.urlopen(req) as resp:
                    raw_body = resp.read().decode("utf-8")

                events = raw_body.strip().split("\n\n")
                for event in events:
                    lines = [l[5:] if l.startswith("data:") else l
                             for l in event.splitlines()
                             if l.startswith("data:") or (l and not l.startswith(":"))]
                    payload = "".join(lines).strip()
                    if not payload:
                        continue
                    try:
                        msg = json.loads(payload)
                        event_type = msg.get("type") or msg.get("event")
                        if event_type == "data":
                            for point in msg.get("data", []):
                                if point.get("value") is not None:
                                    data_points.append({
                                        "tsId":        point.get("tsId"),
                                        "value":       point.get("value"),
                                        "timestampMs": msg.get("logicalTimestampMs"),
                                    })
                        elif event_type == "metadata":
                            tsid = msg.get("tsId")
                            if tsid:
                                metadata[tsid] = msg.get("properties", {})
                        elif event_type in ("done", "error"):
                            messages.append(msg)
                            break
                        else:
                            messages.append(msg)
                    except json.JSONDecodeError:
                        pass

            except urllib.error.HTTPError as e:
                raise RuntimeError(f"Splunk API error {e.code}: {e.read().decode()}")

            enriched = []
            for pt in data_points:
                meta = metadata.get(pt["tsId"], {})
                enriched.append({**pt, "properties": meta})

            return {
                "dataPoints": enriched,
                "dataPointCount": len(enriched),
                "events": messages,
                "hasData": len(enriched) > 0,
            }

        case _:
            raise ValueError(f"Unknown tool: {name}")


# ── Entry Point ────────────────────────────────────────────────────────────────

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

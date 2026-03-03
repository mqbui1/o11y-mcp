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

ACCESS_TOKEN = os.environ.get("SPLUNK_ACCESS_TOKEN")
REALM = os.environ.get("SPLUNK_REALM", "us0")

if not ACCESS_TOKEN:
    print("Error: SPLUNK_ACCESS_TOKEN environment variable is required.", file=sys.stderr)
    sys.exit(1)

BASE_URL   = f"https://api.{REALM}.signalfx.com"
APP_URL    = f"https://app.{REALM}.signalfx.com"
STREAM_URL = f"https://stream.{REALM}.signalfx.com"
INGEST_URL = f"https://ingest.{REALM}.signalfx.com"

# ── HTTP Helper ────────────────────────────────────────────────────────────────

def splunk_request(
    method: str,
    path: str,
    body: dict | None = None,
    base_url: str = BASE_URL,
    extra_headers: dict | None = None,
) -> Any:
    url = f"{base_url}{path}"
    headers = {
        "X-SF-Token": ACCESS_TOKEN,
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
            description="Create a new detector with SignalFlow program text and alert rules.",
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
            description="Create a new dashboard.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name":        {"type": "string"},
                    "description": {"type": "string"},
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
            name="get_chart",
            description="Get details of a specific chart.",
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
            description="Search for events by time range and optional filters.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query":     {"type": "string",  "description": "Search query to filter events"},
                    "startTime": {"type": "integer", "description": "Start time in ms since epoch"},
                    "endTime":   {"type": "integer", "description": "End time in ms since epoch"},
                    "limit":     {"type": "integer", "description": "Max results (default 100)"},
                    "offset":    {"type": "integer"},
                },
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
                        "description": "Only return traces longer than this duration (ms)",
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
            body = {k: v for k, v in {
                "name": args.get("name"), "description": args.get("description"),
                "signalFlowText": args.get("signalFlowText"), "rules": args.get("rules"),
                "tags": args.get("tags"), "teams": args.get("teams"),
                "programOptions": args.get("programOptions"),
            }.items() if v is not None}
            return splunk_request("POST", "/v2/detector", body)
        case "update_detector":
            detector_id = args.pop("detector_id")
            return splunk_request("PUT", f"/v2/detector/{detector_id}",
                                  {k: v for k, v in args.items() if v is not None})
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
            body = {k: v for k, v in {
                "name": args.get("name"), "description": args.get("description"),
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
        case "get_chart":
            return splunk_request("GET", f"/v2/chart/{args['chart_id']}")
        case "list_charts_in_dashboard":
            return splunk_request("GET", f"/v2/dashboard/{args['dashboard_id']}/chart")

        # ── Metrics ───────────────────────────────────────────────────────────
        case "search_metrics":
            return splunk_request("GET", "/v2/metric" + qs({
                "query": args["query"], "limit": args.get("limit"), "offset": args.get("offset"),
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
            return splunk_request("GET", "/v2/organization/token" + qs({
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
            return splunk_request("GET", "/v2/event" + qs({
                "query":     args.get("query"),
                "startTime": args.get("startTime"),
                "endTime":   args.get("endTime"),
                "limit":     args.get("limit"),
                "offset":    args.get("offset"),
            }))
        case "get_event":
            return splunk_request("GET", f"/v2/event/{args['event_id']}")
        case "send_custom_event":
            event = {k: v for k, v in {
                "eventType":  args["eventType"],
                "category":   args["category"],
                "dimensions": args.get("dimensions", {}),
                "properties": args.get("properties", {}),
                "timestamp":  args.get("timestamp", int(time.time() * 1000)),
            }.items() if v is not None}
            return splunk_request("POST", "/v2/event", event)

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
            start_ms = args.get("startTimeMs")
            end_ms = args.get("endTimeMs")
            if not start_ms or not end_ms:
                now_ms = int(time.time() * 1000)
                start_ms = now_ms - 3_600_000
                end_ms = now_ms
            return splunk_request(
                "GET",
                "/v2/apm/profiling/v2/traceSnapshotSummaries" + qs({
                    "traceId": trace_id,
                    "from": start_ms,
                    "to": end_ms,
                }),
                base_url=APP_URL,
            )

        case "get_trace_analysis":
            return splunk_request("GET", f"/v2/apm/traces/{args['trace_id']}/analysis")

        case "search_traces":
            # Use traceSnapshotSummaries search endpoint discovered from UI network traffic
            body = {k: v for k, v in {
                "services":      args.get("services"),
                "operations":    args.get("operations"),
                "tags":          args.get("tags"),
                "startTimeMs":   args.get("startTimeMs"),
                "endTimeMs":     args.get("endTimeMs"),
                "minDurationMs": args.get("minDurationMs"),
                "maxDurationMs": args.get("maxDurationMs"),
                "limit":         args.get("limit", 20),
            }.items() if v is not None}
            return splunk_request("POST", "/v2/apm/traceSnapshotSummaries/search", body)

        case "search_trace_span_tags":
            body = {k: v for k, v in {
                "services":    args.get("services"),
                "operations":  args.get("operations"),
                "startTimeMs": args.get("startTimeMs"),
                "endTimeMs":   args.get("endTimeMs"),
                "tags":        args.get("tags"),
            }.items() if v is not None}
            return splunk_request("POST", "/v2/apm/traces/spantags", body)

        case "list_trace_services":
            # FIXED: Use POST /v2/apm/traces/services with JSON body (not GET with query params)
            body = {k: v for k, v in {
                "services": args.get("services"),
            }.items() if v is not None}
            return splunk_request("POST", "/v2/apm/traces/services", body)

        case "get_trace_outliers":
            body = {k: v for k, v in {
                "services":    args.get("services"),
                "operations":  args.get("operations"),
                "startTimeMs": args.get("startTimeMs"),
                "endTimeMs":   args.get("endTimeMs"),
                "tags":        args.get("tags"),
                "limit":       args.get("limit", 20),
            }.items() if v is not None}
            return splunk_request("POST", "/v2/apm/traces/outliers", body)

        case "get_service_map_for_trace":
            return splunk_request("GET", f"/v2/servicemap/trace/{args['trace_id']}")

        case "search_service_map":
            body = {k: v for k, v in {
                "services":    args.get("services"),
                "operations":  args.get("operations"),
                "startTimeMs": args.get("startTimeMs"),
                "endTimeMs":   args.get("endTimeMs"),
                "tags":        args.get("tags"),
            }.items() if v is not None}
            return splunk_request("POST", "/v2/apm/traces/servicemap", body)

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
                    return splunk_request("POST", "/v2/apm/graphql?op=TraceFullDetailsLessValidation", gql_body, base_url=APP_URL)
        # ── SignalFlow ────────────────────────────────────────────────────────
        case "execute_signalflow":
            now_ms = int(time.time() * 1000)
            body = {k: v for k, v in {
                "programText": args["program"],
                "start":      args.get("start", now_ms - 3_600_000),
                "stop":       args.get("stop", now_ms),
                "resolution": args.get("resolution"),
                "maxDelay":   args.get("maxDelay"),
                "immediate":  args.get("immediate", True),
            }.items() if v is not None}
            return splunk_request("POST", "/v2/signalflow/execute", body, base_url=STREAM_URL)

        case _:
            raise ValueError(f"Unknown tool: {name}")


# ── Entry Point ────────────────────────────────────────────────────────────────

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

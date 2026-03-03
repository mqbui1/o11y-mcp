# Splunk Observability Cloud MCP Server (Python)

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server that exposes the [Splunk Observability Cloud API](https://dev.splunk.com/observability/docs) as tools for Claude and other MCP-compatible AI assistants.

Uses only the Python standard library + the official `mcp` package. No extra HTTP dependencies needed.

## Tools Included

| Category | Tools |
|---|---|
| **Detectors** | list, get, create, update, delete, get incidents |
| **Incidents/Alerts** | list, get, clear |
| **Dashboards** | list, get, create, delete |
| **Dashboard Groups** | list, get |
| **Charts** | get, list by dashboard |
| **Metrics** | search, get metadata |
| **Metric Time Series** | search, get metadata |
| **Dimensions** | search, get, update |
| **Teams** | list, get, create |
| **Muting Rules** | list, create, delete |
| **Organization** | get org info, list tokens |
| **SignalFlow** | execute ad-hoc analytics queries |

## Requirements

- Python 3.10+ (uses `match` statement)

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
# or
pip install mcp
```

### 2. Get your credentials

- **Access Token**: Splunk Observability Cloud → Settings → Access Tokens. Create or copy an org-level token.
- **Realm**: Found at Settings → Profile (e.g. `us0`, `us1`, `eu0`, `ap0`, `ap1`, `au0`).

### 3. Configure Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "splunk-observability": {
      "command": "python3",
      "args": ["/absolute/path/to/splunk-observability-mcp-py/server.py"],
      "env": {
        "SPLUNK_ACCESS_TOKEN": "your-access-token-here",
        "SPLUNK_REALM": "us0"
      }
    }
  }
}
```

**Config file locations:**
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`

### 4. Restart Claude Desktop

After saving the config, restart Claude Desktop and the Splunk tools will be available.

### Optional: Use `uv` for isolated dependencies

If you use [uv](https://github.com/astral-sh/uv):

```json
{
  "mcpServers": {
    "splunk-observability": {
      "command": "uv",
      "args": [
        "run",
        "--with", "mcp",
        "/absolute/path/to/server.py"
      ],
      "env": {
        "SPLUNK_ACCESS_TOKEN": "your-access-token-here",
        "SPLUNK_REALM": "us0"
      }
    }
  }
}
```

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `SPLUNK_ACCESS_TOKEN` | ✅ Yes | — | Org-level API access token |
| `SPLUNK_REALM` | No | `us0` | Your Splunk realm |

## Example Prompts

Once connected, try asking Claude:

- *"List all my active detectors"*
- *"Show me all firing incidents right now"*
- *"Mute alerts for host=web-01 for the next 2 hours"*
- *"Execute a SignalFlow query: data('cpu.utilization').mean().publish()"*
- *"Search for all metrics with 'error' in the name"*
- *"List all dashboards tagged 'production'"*
- *"What teams exist in my organization?"*

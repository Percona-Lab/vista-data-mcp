# VISTA Data MCP Server

Read-only MCP server for querying **ClickHouse** (product telemetry) and **Elasticsearch** (download analytics). Built for [Percona VISTA](https://github.com/Percona-Lab/VISTA).

Both data sources are optional — configure one or both depending on what you have access to.

## Install (one command)

```bash
curl -fsSL https://raw.githubusercontent.com/Percona-Lab/vista-data-mcp/main/install-vista-data-mcp | bash
```

The installer will:
1. Install `uv` if needed
2. Clone this repo to `~/vista-data-mcp`
3. Prompt for your ClickHouse and/or Elasticsearch credentials
4. Auto-detect and configure Claude Desktop, Claude Code, and CLI
5. Persist across reboots — the MCP config points to the cloned repo on disk

Re-run the same command to update or change credentials.

---

## Tools

### ClickHouse (telemetry)

| Tool | Description |
|------|-------------|
| `query_clickhouse` | Run any read-only SQL (SELECT, SHOW, DESCRIBE, EXPLAIN) |
| `ch_list_databases` | Show all accessible databases |
| `ch_list_tables` | Show tables in a database |
| `ch_describe_table` | Show column names, types, and comments |
| `ch_sample_data` | Get sample rows from a table |

### Elasticsearch (downloads)

| Tool | Description |
|------|-------------|
| `search_elasticsearch` | Run an Elasticsearch query (JSON DSL) |
| `es_list_indices` | Show all indices with doc counts and sizes |
| `es_get_mapping` | Show field mapping (schema) for an index |
| `es_sample_data` | Get sample documents from an index |

All results are returned as Markdown tables. Only read-only queries are allowed.

---

## Manual Install (alternative)

If you prefer not to use the installer:

### Claude Code (CLI)

```bash
claude mcp add vista-data \
  -e CLICKHOUSE_HOST=your-ch-host \
  -e CLICKHOUSE_PORT=8443 \
  -e CLICKHOUSE_USER=default \
  -e CLICKHOUSE_PASSWORD=your-ch-password \
  -e CLICKHOUSE_DATABASE=default \
  -e CLICKHOUSE_SECURE=true \
  -e ES_HOST=your-es-host \
  -e ES_PORT=9200 \
  -e ES_USER=your-es-user \
  -e ES_PASSWORD=your-es-password \
  -e ES_SECURE=true \
  -- uvx --from git+https://github.com/Percona-Lab/vista-data-mcp vista-data-mcp
```

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "vista-data": {
      "command": "uvx",
      "args": [
        "--from", "git+https://github.com/Percona-Lab/vista-data-mcp",
        "vista-data-mcp"
      ],
      "env": {
        "CLICKHOUSE_HOST": "your-ch-host",
        "CLICKHOUSE_PORT": "8443",
        "CLICKHOUSE_USER": "default",
        "CLICKHOUSE_PASSWORD": "your-ch-password",
        "CLICKHOUSE_DATABASE": "default",
        "CLICKHOUSE_SECURE": "true",
        "ES_HOST": "your-es-host",
        "ES_PORT": "9200",
        "ES_USER": "your-es-user",
        "ES_PASSWORD": "your-es-password",
        "ES_SECURE": "true"
      }
    }
  }
}
```

### Development

```bash
git clone https://github.com/Percona-Lab/vista-data-mcp.git
cd vista-data-mcp
cp .env.example .env
# Edit .env with your credentials
uv run mcp_server.py
```

---

## Safety

- **Read-only**: ClickHouse allows only `SELECT`, `SHOW`, `DESCRIBE`, `EXPLAIN`. Elasticsearch uses search API only (no indexing).
- **Mutation blocking**: `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE` are rejected
- **Row/hit limits**: Results capped at 500 (configurable via `CLICKHOUSE_MAX_ROWS` / `ES_MAX_HITS`)
- **Query timeout**: 30 seconds default (configurable via `CLICKHOUSE_QUERY_TIMEOUT` / `ES_QUERY_TIMEOUT`)
- **Identifier sanitization**: Database and table names validated against injection

## Environment Variables

### ClickHouse

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `CLICKHOUSE_HOST` | Yes* | — | ClickHouse server hostname |
| `CLICKHOUSE_PORT` | No | `8443` | HTTP(S) port |
| `CLICKHOUSE_USER` | No | `default` | Username |
| `CLICKHOUSE_PASSWORD` | No | `""` | Password |
| `CLICKHOUSE_DATABASE` | No | `default` | Default database |
| `CLICKHOUSE_SECURE` | No | `true` | Use HTTPS |
| `CLICKHOUSE_QUERY_TIMEOUT` | No | `30` | Timeout in seconds |
| `CLICKHOUSE_MAX_ROWS` | No | `500` | Max rows per query |

### Elasticsearch

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ES_HOST` | Yes* | — | Elasticsearch hostname |
| `ES_PORT` | No | `9200` | Port |
| `ES_USER` | No | `""` | Username (for basic auth) |
| `ES_PASSWORD` | No | `""` | Password |
| `ES_SECURE` | No | `true` | Use HTTPS |
| `ES_VERIFY_CERTS` | No | `true` | Verify SSL certificates |
| `ES_QUERY_TIMEOUT` | No | `30` | Timeout in seconds |
| `ES_MAX_HITS` | No | `500` | Max hits per search |

*Only required if you want to use that data source. Tools for unconfigured sources return a helpful message.

---

## Part of the Alpine Toolkit

Built with [CAIRN](https://github.com/Percona-Lab/CAIRN) for [VISTA](https://github.com/Percona-Lab/VISTA).

## License

Apache 2.0

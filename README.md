# ClickHouse MCP Server

Read-only MCP server for querying ClickHouse databases. Built for [Percona VISTA](https://github.com/Percona-Lab/VISTA) but works with any ClickHouse instance.

**Tools exposed:**

| Tool | Description |
|------|-------------|
| `query_clickhouse` | Run any read-only SQL query (SELECT, SHOW, DESCRIBE, EXPLAIN) |
| `list_databases` | Show all accessible databases |
| `list_tables` | Show tables in a database |
| `describe_table` | Show column names, types, and comments |
| `sample_data` | Get sample rows from a table (up to 100) |

All results are returned as Markdown tables. Only read-only queries are allowed — mutations are rejected.

---

## Quick Start

### 1. Set your credentials

Copy `.env.example` to `.env` and fill in your ClickHouse connection details:

```bash
cp .env.example .env
# Edit .env with your host, user, password, database
```

### 2. Install in Claude Code (CLI)

```bash
claude mcp add clickhouse -e CLICKHOUSE_HOST=your-host -e CLICKHOUSE_PORT=8443 -e CLICKHOUSE_USER=default -e CLICKHOUSE_PASSWORD=your-password -e CLICKHOUSE_DATABASE=default -e CLICKHOUSE_SECURE=true -- uvx --from git+https://github.com/Percona-Lab/clickhouse-mcp-server clickhouse-mcp-server
```

### 3. Install in Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "clickhouse": {
      "command": "uvx",
      "args": [
        "--from", "git+https://github.com/Percona-Lab/clickhouse-mcp-server",
        "clickhouse-mcp-server"
      ],
      "env": {
        "CLICKHOUSE_HOST": "your-host",
        "CLICKHOUSE_PORT": "8443",
        "CLICKHOUSE_USER": "default",
        "CLICKHOUSE_PASSWORD": "your-password",
        "CLICKHOUSE_DATABASE": "default",
        "CLICKHOUSE_SECURE": "true"
      }
    }
  }
}
```

Restart Claude Desktop after editing.

### 4. Run locally (development)

```bash
git clone https://github.com/Percona-Lab/clickhouse-mcp-server.git
cd clickhouse-mcp-server
cp .env.example .env
# Edit .env with your credentials

# Run with uv
uv run mcp_server.py

# Or install and run
uv pip install -e .
clickhouse-mcp-server
```

---

## Safety

- **Read-only**: Only `SELECT`, `SHOW`, `DESCRIBE`, `EXPLAIN`, and `WITH` statements are allowed
- **Mutation blocking**: `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE` and other mutation keywords are rejected
- **Row limit**: Results capped at 500 rows (configurable via `CLICKHOUSE_MAX_ROWS`)
- **Query timeout**: 30 seconds default (configurable via `CLICKHOUSE_QUERY_TIMEOUT`)
- **Identifier sanitization**: Database and table names are validated against injection

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `CLICKHOUSE_HOST` | Yes | — | ClickHouse server hostname |
| `CLICKHOUSE_PORT` | No | `8443` | HTTP(S) port |
| `CLICKHOUSE_USER` | No | `default` | Username |
| `CLICKHOUSE_PASSWORD` | No | `""` | Password |
| `CLICKHOUSE_DATABASE` | No | `default` | Default database |
| `CLICKHOUSE_SECURE` | No | `true` | Use HTTPS (`true`/`false`) |
| `CLICKHOUSE_QUERY_TIMEOUT` | No | `30` | Query timeout in seconds |
| `CLICKHOUSE_MAX_ROWS` | No | `500` | Max rows returned per query |

---

## Part of the Alpine Toolkit

Built with [CAIRN](https://github.com/Percona-Lab/CAIRN) for [VISTA](https://github.com/Percona-Lab/VISTA).

## License

Apache 2.0

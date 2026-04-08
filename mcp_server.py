"""ClickHouse MCP Server — read-only access to ClickHouse for LLM tool use.

Part of Percona's VISTA project.
https://github.com/Percona-Lab/VISTA
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from connector import ClickHouseConnector

mcp = FastMCP(
    "clickhouse",
    description=(
        "Read-only access to a ClickHouse database. "
        "Query product telemetry, download stats, version distribution, "
        "and other analytics data."
    ),
)

_ch = ClickHouseConnector()


# ── Tools ────────────────────────────────────────────────────────────


@mcp.tool()
def query_clickhouse(sql: str) -> str:
    """Run a read-only SQL query against ClickHouse and return results as a Markdown table.

    Only SELECT, SHOW, DESCRIBE, and EXPLAIN statements are allowed.
    Results are capped at 500 rows by default.

    Args:
        sql: A read-only SQL statement (SELECT, SHOW, DESCRIBE, EXPLAIN).

    Examples:
        - SELECT count() FROM telemetry WHERE product = 'MySQL'
        - SELECT version, count() as n FROM telemetry GROUP BY version ORDER BY n DESC
        - SHOW TABLES
    """
    try:
        return _ch.query(sql)
    except ValueError as e:
        return f"**Error:** {e}"
    except Exception as e:
        return f"**Query failed:** {type(e).__name__}: {e}"


@mcp.tool()
def list_databases() -> str:
    """List all databases accessible in the ClickHouse instance."""
    try:
        return _ch.list_databases()
    except Exception as e:
        return f"**Error:** {type(e).__name__}: {e}"


@mcp.tool()
def list_tables(database: str | None = None) -> str:
    """List all tables in a ClickHouse database.

    Args:
        database: Database name. If omitted, lists tables in the default database.
    """
    try:
        return _ch.list_tables(database)
    except Exception as e:
        return f"**Error:** {type(e).__name__}: {e}"


@mcp.tool()
def describe_table(table: str, database: str | None = None) -> str:
    """Show the schema (columns, types, comments) of a ClickHouse table.

    Args:
        table: Table name.
        database: Database name. If omitted, uses the default database.
    """
    try:
        return _ch.describe_table(table, database)
    except Exception as e:
        return f"**Error:** {type(e).__name__}: {e}"


@mcp.tool()
def sample_data(table: str, database: str | None = None, limit: int = 10) -> str:
    """Get sample rows from a ClickHouse table (up to 100 rows).

    Useful for understanding data structure before writing queries.

    Args:
        table: Table name.
        database: Database name. If omitted, uses the default database.
        limit: Number of rows to return (1-100, default 10).
    """
    try:
        return _ch.sample_data(table, database, limit)
    except Exception as e:
        return f"**Error:** {type(e).__name__}: {e}"


# ── Entry point ──────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()

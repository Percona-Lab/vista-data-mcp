"""VISTA Data MCP Server — read-only access to ClickHouse + Elasticsearch.

Unified MCP server for Percona product telemetry (ClickHouse) and
download/package data (Elasticsearch). Part of the VISTA project.

https://github.com/Percona-Lab/VISTA
"""

from __future__ import annotations

import os
from pathlib import Path

# Load credentials from .env file if DOTENV_PATH is set or .env exists next to this script
_dotenv_path = os.getenv("DOTENV_PATH") or str(Path(__file__).parent / ".env")
if Path(_dotenv_path).is_file():
    with open(_dotenv_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip()
                if not os.getenv(key):  # don't override existing env vars
                    os.environ[key] = value

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "vista-data",
    instructions=(
        "Read-only access to Percona product data across ClickHouse (telemetry: "
        "active instances, version distribution, storage engines, deployment types) "
        "and Elasticsearch (downloads: product downloads by type, OS, package, growth rates). "
        "Use ClickHouse tools for telemetry queries and Elasticsearch tools for download data."
    ),
)


# ── ClickHouse tools ─────────────────────────────────────────────────

def _ch_enabled() -> bool:
    return bool(os.getenv("CLICKHOUSE_HOST"))


_ch = None


def _ch_instance():
    global _ch
    if _ch is None:
        from ch_connector import ClickHouseConnector
        _ch = ClickHouseConnector()
    return _ch


@mcp.tool()
def query_clickhouse(sql: str) -> str:
    """Run a read-only SQL query against ClickHouse (telemetry data).

    Only SELECT, SHOW, DESCRIBE, and EXPLAIN statements are allowed.
    Results are capped at 500 rows by default.

    Use this for product telemetry: active instances, version distribution,
    storage engines, deployment types, CPU architecture, cluster metrics.

    Args:
        sql: A read-only SQL statement.

    Examples:
        - SELECT count() FROM telemetry WHERE product = 'MySQL'
        - SELECT version, count() as n FROM telemetry GROUP BY version ORDER BY n DESC
        - SHOW TABLES
    """
    if not _ch_enabled():
        return "**ClickHouse not configured.** Set CLICKHOUSE_HOST environment variable."
    try:
        return _ch_instance().query(sql)
    except ValueError as e:
        return f"**Error:** {e}"
    except Exception as e:
        return f"**Query failed:** {type(e).__name__}: {e}"


@mcp.tool()
def ch_list_databases() -> str:
    """List all databases accessible in the ClickHouse instance."""
    if not _ch_enabled():
        return "**ClickHouse not configured.** Set CLICKHOUSE_HOST environment variable."
    try:
        return _ch_instance().list_databases()
    except Exception as e:
        return f"**Error:** {type(e).__name__}: {e}"


@mcp.tool()
def ch_list_tables(database: str | None = None) -> str:
    """List all tables in a ClickHouse database.

    Args:
        database: Database name. If omitted, lists tables in the default database.
    """
    if not _ch_enabled():
        return "**ClickHouse not configured.** Set CLICKHOUSE_HOST environment variable."
    try:
        return _ch_instance().list_tables(database)
    except Exception as e:
        return f"**Error:** {type(e).__name__}: {e}"


@mcp.tool()
def ch_describe_table(table: str, database: str | None = None) -> str:
    """Show the schema (columns, types, comments) of a ClickHouse table.

    Args:
        table: Table name.
        database: Database name. If omitted, uses the default database.
    """
    if not _ch_enabled():
        return "**ClickHouse not configured.** Set CLICKHOUSE_HOST environment variable."
    try:
        return _ch_instance().describe_table(table, database)
    except Exception as e:
        return f"**Error:** {type(e).__name__}: {e}"


@mcp.tool()
def ch_sample_data(table: str, database: str | None = None, limit: int = 10) -> str:
    """Get sample rows from a ClickHouse table (up to 100 rows).

    Useful for understanding telemetry data structure before writing queries.

    Args:
        table: Table name.
        database: Database name. If omitted, uses the default database.
        limit: Number of rows to return (1-100, default 10).
    """
    if not _ch_enabled():
        return "**ClickHouse not configured.** Set CLICKHOUSE_HOST environment variable."
    try:
        return _ch_instance().sample_data(table, database, limit)
    except Exception as e:
        return f"**Error:** {type(e).__name__}: {e}"


# ── Elasticsearch tools ──────────────────────────────────────────────

def _es_enabled() -> bool:
    return bool(os.getenv("ES_HOST"))


_es = None


def _es_instance():
    global _es
    if _es is None:
        from es_connector import ElasticsearchConnector
        _es = ElasticsearchConnector()
    return _es


@mcp.tool()
def search_elasticsearch(index: str, query_body: str, size: int | None = None) -> str:
    """Run an Elasticsearch query (JSON DSL) against download/package data.

    Use this for product download data: downloads by product, package type,
    OS, components, growth rates, EOL packages, Pro-builds.

    Args:
        index: The Elasticsearch index to search.
        query_body: A JSON string containing the Elasticsearch query DSL.
            Supports match, term, range, bool, aggregations, etc.
        size: Max documents to return (default 500).

    Examples:
        - {"query": {"match": {"product": "postgresql"}}, "size": 20}
        - {"size": 0, "aggs": {"by_package": {"terms": {"field": "package_type"}}}}
        - {"query": {"range": {"date": {"gte": "2025-01-01"}}}}
    """
    if not _es_enabled():
        return "**Elasticsearch not configured.** Set ES_HOST environment variable."
    try:
        return _es_instance().search(index, query_body, size)
    except Exception as e:
        return f"**Query failed:** {type(e).__name__}: {e}"


@mcp.tool()
def es_list_indices() -> str:
    """List all Elasticsearch indices with document counts and sizes.

    Use this to discover available download/package data indices.
    """
    if not _es_enabled():
        return "**Elasticsearch not configured.** Set ES_HOST environment variable."
    try:
        return _es_instance().list_indices()
    except Exception as e:
        return f"**Error:** {type(e).__name__}: {e}"


@mcp.tool()
def es_get_mapping(index: str) -> str:
    """Show the field mapping (schema) for an Elasticsearch index.

    Args:
        index: The index name to inspect.
    """
    if not _es_enabled():
        return "**Elasticsearch not configured.** Set ES_HOST environment variable."
    try:
        return _es_instance().get_mapping(index)
    except Exception as e:
        return f"**Error:** {type(e).__name__}: {e}"


@mcp.tool()
def es_sample_data(index: str, size: int = 10) -> str:
    """Get sample documents from an Elasticsearch index (up to 100).

    Useful for understanding download data structure before writing queries.

    Args:
        index: The index name.
        size: Number of documents to return (1-100, default 10).
    """
    if not _es_enabled():
        return "**Elasticsearch not configured.** Set ES_HOST environment variable."
    try:
        return _es_instance().sample_data(index, size)
    except Exception as e:
        return f"**Error:** {type(e).__name__}: {e}"


# ── Entry point ──────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()

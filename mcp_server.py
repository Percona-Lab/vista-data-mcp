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


def _friendly_error(source: str, e: Exception) -> str:
    """Return a user-friendly error message based on exception type."""
    etype = type(e).__name__
    msg = str(e)
    if "ConnectionError" in etype or "ConnectionTimeout" in etype or "timed out" in msg.lower():
        return (
            f"**{source} connection failed.** Cannot reach the server.\n\n"
            f"**If using the remote server (recommended setup):** Connect to Percona VPN and try again.\n"
            f"**If running locally with your own credentials:** Check that the host in your .env file is correct "
            f"and reachable from your network.\n\n"
            f"_Technical detail: {etype}: {msg}_"
        )
    if "Authentication" in etype or "401" in msg or "403" in msg:
        return (
            f"**{source} authentication failed.** Your credentials are incorrect or expired. "
            f"Check the username and password in your .env file. "
            f"If you don't have credentials, switch to the remote server instead — "
            f"no credentials needed, just VPN. See https://github.com/Percona-Lab/vista-data-mcp\n\n"
            f"_Technical detail: {etype}: {msg}_"
        )
    return f"**{source} query failed:** {etype}: {msg}"


_NOT_CONFIGURED_MSG = (
    "**{source} not configured.** Run the installer to set up the data connection:\n"
    "```\n"
    "curl -fsSL https://raw.githubusercontent.com/Percona-Lab/vista-data-mcp/main/install-vista-data-mcp | bash\n"
    "```\n"
    "Choose Remote (default) for VPN access, or Local if you have your own credentials.\n"
    "See https://github.com/Percona-Lab/vista-data-mcp for details."
)

# ── Remote proxy mode ───────────────────────────────────────────────
# When REMOTE_SSE_URL is set, tool calls are forwarded to a remote MCP
# server via SSE. This lets the server start instantly (tools register)
# even when off VPN — connection is attempted lazily per tool call.

_REMOTE_SSE_URL = os.getenv("REMOTE_SSE_URL")

_VPN_REQUIRED_MSG = (
    "**Cannot reach the VISTA data server.** Connect to Percona VPN and try again.\n\n"
    "The data MCP is configured in remote mode — it connects to a shared server "
    "that is only accessible on the Percona internal network.\n\n"
    "_If you need offline access, re-run the installer and choose Local mode "
    "with your own credentials._"
)


async def _call_remote(tool_name: str, arguments: dict) -> str:
    """Forward a tool call to the remote MCP server via SSE."""
    from mcp.client.sse import sse_client
    from mcp import ClientSession

    try:
        async with sse_client(url=_REMOTE_SSE_URL) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                if result.content:
                    parts = [
                        block.text for block in result.content
                        if hasattr(block, "text")
                    ]
                    return "\n".join(parts) if parts else "No results."
                return "No results returned."
    except Exception as e:
        msg = str(e).lower()
        if any(k in msg for k in [
            "nodename", "connecterror", "connect error",
            "timed out", "connection refused", "unreachable",
            "name or service not known", "no route to host",
        ]):
            return _VPN_REQUIRED_MSG
        return f"**Remote query failed:** {type(e).__name__}: {e}"

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
async def query_clickhouse(sql: str) -> str:
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
        if _REMOTE_SSE_URL:
            return await _call_remote("query_clickhouse", {"sql": sql})
        return _NOT_CONFIGURED_MSG.format(source="ClickHouse")
    try:
        return _ch_instance().query(sql)
    except ValueError as e:
        return f"**Error:** {e}"
    except Exception as e:
        return _friendly_error("ClickHouse", e)


@mcp.tool()
async def ch_list_databases() -> str:
    """List all databases accessible in the ClickHouse instance."""
    if not _ch_enabled():
        if _REMOTE_SSE_URL:
            return await _call_remote("ch_list_databases", {})
        return _NOT_CONFIGURED_MSG.format(source="ClickHouse")
    try:
        return _ch_instance().list_databases()
    except Exception as e:
        return _friendly_error("ClickHouse", e)


@mcp.tool()
async def ch_list_tables(database: str | None = None) -> str:
    """List all tables in a ClickHouse database.

    Args:
        database: Database name. If omitted, lists tables in the default database.
    """
    if not _ch_enabled():
        if _REMOTE_SSE_URL:
            return await _call_remote("ch_list_tables", {"database": database} if database else {})
        return _NOT_CONFIGURED_MSG.format(source="ClickHouse")
    try:
        return _ch_instance().list_tables(database)
    except Exception as e:
        return _friendly_error("ClickHouse", e)


@mcp.tool()
async def ch_describe_table(table: str, database: str | None = None) -> str:
    """Show the schema (columns, types, comments) of a ClickHouse table.

    Args:
        table: Table name.
        database: Database name. If omitted, uses the default database.
    """
    if not _ch_enabled():
        if _REMOTE_SSE_URL:
            args = {"table": table}
            if database:
                args["database"] = database
            return await _call_remote("ch_describe_table", args)
        return _NOT_CONFIGURED_MSG.format(source="ClickHouse")
    try:
        return _ch_instance().describe_table(table, database)
    except Exception as e:
        return _friendly_error("ClickHouse", e)


@mcp.tool()
async def ch_sample_data(table: str, database: str | None = None, limit: int = 10) -> str:
    """Get sample rows from a ClickHouse table (up to 100 rows).

    Useful for understanding telemetry data structure before writing queries.

    Args:
        table: Table name.
        database: Database name. If omitted, uses the default database.
        limit: Number of rows to return (1-100, default 10).
    """
    if not _ch_enabled():
        if _REMOTE_SSE_URL:
            args = {"table": table, "limit": limit}
            if database:
                args["database"] = database
            return await _call_remote("ch_sample_data", args)
        return _NOT_CONFIGURED_MSG.format(source="ClickHouse")
    try:
        return _ch_instance().sample_data(table, database, limit)
    except Exception as e:
        return _friendly_error("ClickHouse", e)


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
async def search_elasticsearch(index: str, query_body: str, size: int | None = None) -> str:
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
        if _REMOTE_SSE_URL:
            args = {"index": index, "query_body": query_body}
            if size is not None:
                args["size"] = size
            return await _call_remote("search_elasticsearch", args)
        return _NOT_CONFIGURED_MSG.format(source="Elasticsearch")
    try:
        return _es_instance().search(index, query_body, size)
    except Exception as e:
        return _friendly_error("Elasticsearch", e)


@mcp.tool()
async def es_list_indices() -> str:
    """List all Elasticsearch indices with document counts and sizes.

    Use this to discover available download/package data indices.
    """
    if not _es_enabled():
        if _REMOTE_SSE_URL:
            return await _call_remote("es_list_indices", {})
        return _NOT_CONFIGURED_MSG.format(source="Elasticsearch")
    try:
        return _es_instance().list_indices()
    except Exception as e:
        return _friendly_error("Elasticsearch", e)


@mcp.tool()
async def es_get_mapping(index: str) -> str:
    """Show the field mapping (schema) for an Elasticsearch index.

    Args:
        index: The index name to inspect.
    """
    if not _es_enabled():
        if _REMOTE_SSE_URL:
            return await _call_remote("es_get_mapping", {"index": index})
        return _NOT_CONFIGURED_MSG.format(source="Elasticsearch")
    try:
        return _es_instance().get_mapping(index)
    except Exception as e:
        return _friendly_error("Elasticsearch", e)


@mcp.tool()
async def es_sample_data(index: str, size: int = 10) -> str:
    """Get sample documents from an Elasticsearch index (up to 100).

    Useful for understanding download data structure before writing queries.

    Args:
        index: The index name.
        size: Number of documents to return (1-100, default 10).
    """
    if not _es_enabled():
        if _REMOTE_SSE_URL:
            return await _call_remote("es_sample_data", {"index": index, "size": size})
        return _NOT_CONFIGURED_MSG.format(source="Elasticsearch")
    try:
        return _es_instance().sample_data(index, size)
    except Exception as e:
        return _friendly_error("Elasticsearch", e)


# ── Entry point ──────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()

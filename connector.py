"""ClickHouse connector — thin wrapper around clickhouse-connect.

Handles connection lifecycle, enforces read-only access, and formats
query results as Markdown tables for LLM consumption.
"""

from __future__ import annotations

import os
import re
from typing import Any

import clickhouse_connect
from clickhouse_connect.driver.client import Client


# Statements that are safe to execute (read-only)
_SAFE_PREFIXES = (
    "SELECT",
    "SHOW",
    "DESCRIBE",
    "DESC",
    "EXPLAIN",
    "EXISTS",
    "WITH",  # CTEs starting with WITH ... SELECT
)

# Hard-banned keywords that should never appear at statement level
_BANNED_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|RENAME|ATTACH|DETACH|KILL|GRANT|REVOKE|OPTIMIZE|SYSTEM)\b",
    re.IGNORECASE,
)

DEFAULT_TIMEOUT = int(os.getenv("CLICKHOUSE_QUERY_TIMEOUT", "30"))
DEFAULT_ROW_LIMIT = int(os.getenv("CLICKHOUSE_MAX_ROWS", "500"))


class ClickHouseConnector:
    """Read-only ClickHouse client for MCP tool use."""

    def __init__(self) -> None:
        self._client: Client | None = None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def _get_client(self) -> Client:
        if self._client is None:
            self._client = clickhouse_connect.get_client(
                host=os.environ["CLICKHOUSE_HOST"],
                port=int(os.getenv("CLICKHOUSE_PORT", "8443")),
                username=os.getenv("CLICKHOUSE_USER", "default"),
                password=os.getenv("CLICKHOUSE_PASSWORD", ""),
                database=os.getenv("CLICKHOUSE_DATABASE", "default"),
                secure=os.getenv("CLICKHOUSE_SECURE", "true").lower() == "true",
                connect_timeout=10,
                send_receive_timeout=DEFAULT_TIMEOUT,
            )
        return self._client

    # ------------------------------------------------------------------
    # Safety
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_query(sql: str) -> None:
        """Reject anything that isn't a read-only statement."""
        stripped = sql.strip().rstrip(";").strip()

        # Check for banned keywords anywhere in the statement
        if _BANNED_KEYWORDS.search(stripped):
            raise ValueError(
                f"Query rejected — only read-only statements are allowed. "
                f"Detected a mutation keyword in: {stripped[:120]}..."
            )

        # Verify it starts with an allowed prefix
        upper = stripped.upper()
        if not any(upper.startswith(p) for p in _SAFE_PREFIXES):
            raise ValueError(
                f"Query rejected — must start with one of: {', '.join(_SAFE_PREFIXES)}. "
                f"Got: {stripped[:80]}..."
            )

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    @staticmethod
    def _to_markdown_table(columns: list[str], rows: list[list[Any]]) -> str:
        """Render query results as a Markdown table."""
        if not columns:
            return "_No columns returned._"
        if not rows:
            header = "| " + " | ".join(columns) + " |"
            sep = "| " + " | ".join("---" for _ in columns) + " |"
            return f"{header}\n{sep}\n\n_0 rows._"

        header = "| " + " | ".join(columns) + " |"
        sep = "| " + " | ".join("---" for _ in columns) + " |"
        body_lines = []
        for row in rows:
            cells = [str(v) if v is not None else "" for v in row]
            body_lines.append("| " + " | ".join(cells) + " |")
        return "\n".join([header, sep, *body_lines])

    # ------------------------------------------------------------------
    # Public API (used by MCP tools)
    # ------------------------------------------------------------------

    def query(self, sql: str, limit: int | None = None) -> str:
        """Execute a read-only SQL query and return Markdown-formatted results."""
        self._validate_query(sql)

        effective_limit = min(limit or DEFAULT_ROW_LIMIT, DEFAULT_ROW_LIMIT)

        # Append LIMIT if not already present
        if "LIMIT" not in sql.upper():
            sql = f"{sql.rstrip().rstrip(';')} LIMIT {effective_limit}"

        client = self._get_client()
        result = client.query(sql)
        return self._to_markdown_table(result.column_names, result.result_rows)

    def list_databases(self) -> str:
        """List all accessible databases."""
        client = self._get_client()
        result = client.query("SHOW DATABASES")
        dbs = [row[0] for row in result.result_rows]
        return "\n".join(f"- {db}" for db in dbs) if dbs else "_No databases found._"

    def list_tables(self, database: str | None = None) -> str:
        """List tables in a database (defaults to the connected database)."""
        client = self._get_client()
        if database:
            # Sanitize database name — only allow alphanumeric + underscore
            if not re.match(r"^[a-zA-Z0-9_]+$", database):
                raise ValueError(f"Invalid database name: {database}")
            result = client.query(f"SHOW TABLES FROM {database}")
        else:
            result = client.query("SHOW TABLES")
        tables = [row[0] for row in result.result_rows]
        return "\n".join(f"- {t}" for t in tables) if tables else "_No tables found._"

    def describe_table(self, table: str, database: str | None = None) -> str:
        """Show column names, types, and comments for a table."""
        # Sanitize identifiers
        for name in [table, database]:
            if name and not re.match(r"^[a-zA-Z0-9_.]+$", name):
                raise ValueError(f"Invalid identifier: {name}")

        qualified = f"{database}.{table}" if database else table
        client = self._get_client()
        result = client.query(f"DESCRIBE TABLE {qualified}")
        return self._to_markdown_table(result.column_names, result.result_rows)

    def sample_data(self, table: str, database: str | None = None, limit: int = 10) -> str:
        """Get sample rows from a table."""
        for name in [table, database]:
            if name and not re.match(r"^[a-zA-Z0-9_.]+$", name):
                raise ValueError(f"Invalid identifier: {name}")

        qualified = f"{database}.{table}" if database else table
        safe_limit = min(max(1, limit), 100)
        client = self._get_client()
        result = client.query(f"SELECT * FROM {qualified} LIMIT {safe_limit}")
        return self._to_markdown_table(result.column_names, result.result_rows)

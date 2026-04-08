"""Elasticsearch connector — read-only access to Elasticsearch for download/product data.

Handles connection lifecycle, enforces read-only access, and formats
query results as Markdown tables for LLM consumption.
"""

from __future__ import annotations

import json
import os
from typing import Any

from elasticsearch import Elasticsearch


DEFAULT_TIMEOUT = int(os.getenv("ES_QUERY_TIMEOUT", "30"))
DEFAULT_MAX_HITS = int(os.getenv("ES_MAX_HITS", "500"))


class ElasticsearchConnector:
    """Read-only Elasticsearch client for MCP tool use."""

    def __init__(self) -> None:
        self._client: Elasticsearch | None = None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def _get_client(self) -> Elasticsearch:
        if self._client is None:
            host = os.environ["ES_HOST"]
            port = int(os.getenv("ES_PORT", "9200"))
            scheme = "https" if os.getenv("ES_SECURE", "true").lower() == "true" else "http"
            user = os.getenv("ES_USER", "")
            password = os.getenv("ES_PASSWORD", "")

            kwargs: dict[str, Any] = {
                "hosts": [f"{scheme}://{host}:{port}"],
                "request_timeout": DEFAULT_TIMEOUT,
            }

            if user and password:
                kwargs["basic_auth"] = (user, password)

            # Allow self-signed certs if configured
            if os.getenv("ES_VERIFY_CERTS", "true").lower() == "false":
                kwargs["verify_certs"] = False

            self._client = Elasticsearch(**kwargs)
        return self._client

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    @staticmethod
    def _flatten_hit(hit: dict) -> dict:
        """Flatten an ES hit into a simple dict (merge _source with _id)."""
        flat = {"_id": hit.get("_id", "")}
        source = hit.get("_source", {})
        flat.update(source)
        return flat

    @staticmethod
    def _to_markdown_table(rows: list[dict]) -> str:
        """Render a list of flat dicts as a Markdown table."""
        if not rows:
            return "_No results._"

        # Collect all keys preserving order
        columns: list[str] = []
        seen: set[str] = set()
        for row in rows:
            for k in row:
                if k not in seen:
                    columns.append(k)
                    seen.add(k)

        header = "| " + " | ".join(columns) + " |"
        sep = "| " + " | ".join("---" for _ in columns) + " |"
        body_lines = []
        for row in rows:
            cells = []
            for col in columns:
                val = row.get(col, "")
                # Truncate long nested objects
                if isinstance(val, (dict, list)):
                    val = json.dumps(val, default=str)[:120]
                cells.append(str(val) if val is not None else "")
            body_lines.append("| " + " | ".join(cells) + " |")
        return "\n".join([header, sep, *body_lines])

    @staticmethod
    def _format_aggs(aggregations: dict, depth: int = 0) -> str:
        """Recursively format aggregation results as readable Markdown."""
        lines = []
        indent = "  " * depth
        for agg_name, agg_data in aggregations.items():
            if "buckets" in agg_data:
                lines.append(f"{indent}**{agg_name}:**")
                for bucket in agg_data["buckets"]:
                    key = bucket.get("key_as_string", bucket.get("key", ""))
                    doc_count = bucket.get("doc_count", 0)
                    lines.append(f"{indent}- {key}: {doc_count:,}")
                    # Check for sub-aggregations
                    sub_aggs = {
                        k: v
                        for k, v in bucket.items()
                        if isinstance(v, dict) and ("buckets" in v or "value" in v)
                    }
                    if sub_aggs:
                        lines.append(ElasticsearchConnector._format_aggs(sub_aggs, depth + 1))
            elif "value" in agg_data:
                val = agg_data["value"]
                if isinstance(val, float):
                    val = f"{val:,.2f}"
                lines.append(f"{indent}**{agg_name}:** {val}")
            elif "doc_count" in agg_data:
                lines.append(f"{indent}**{agg_name}:** {agg_data['doc_count']:,} docs")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Public API (used by MCP tools)
    # ------------------------------------------------------------------

    def list_indices(self) -> str:
        """List all accessible indices with doc counts and size."""
        client = self._get_client()
        indices = client.cat.indices(format="json", h="index,docs.count,store.size,status")
        if not indices:
            return "_No indices found._"
        # Filter out system indices
        visible = [i for i in indices if not i["index"].startswith(".")]
        visible.sort(key=lambda x: x["index"])
        return self._to_markdown_table(visible)

    def get_mapping(self, index: str) -> str:
        """Show the field mapping (schema) for an index."""
        client = self._get_client()
        mapping = client.indices.get_mapping(index=index)

        lines = [f"**Index: {index}**\n"]
        for idx_name, idx_data in mapping.items():
            props = idx_data.get("mappings", {}).get("properties", {})
            lines.append("| Field | Type | Details |")
            lines.append("| --- | --- | --- |")
            for field, field_data in sorted(props.items()):
                ftype = field_data.get("type", "object")
                details = ""
                if "fields" in field_data:
                    details = f"multi-field: {', '.join(field_data['fields'].keys())}"
                if "properties" in field_data:
                    sub_fields = list(field_data["properties"].keys())[:5]
                    details = f"nested: {', '.join(sub_fields)}{'...' if len(field_data['properties']) > 5 else ''}"
                lines.append(f"| {field} | {ftype} | {details} |")
        return "\n".join(lines)

    def search(self, index: str, query_body: str, size: int | None = None) -> str:
        """Run an Elasticsearch query (JSON DSL) and return results.

        The query_body should be a JSON string containing the ES query DSL.
        Supports match, term, range, bool, aggregations, etc.
        """
        effective_size = min(size or DEFAULT_MAX_HITS, DEFAULT_MAX_HITS)

        body = json.loads(query_body)
        body.setdefault("size", effective_size)

        client = self._get_client()
        result = client.search(index=index, body=body)

        parts = []

        # Total hits
        total = result.get("hits", {}).get("total", {})
        if isinstance(total, dict):
            total_count = total.get("value", 0)
            relation = total.get("relation", "eq")
            parts.append(f"**Total hits:** {total_count:,} ({relation})\n")
        else:
            parts.append(f"**Total hits:** {total}\n")

        # Aggregations (if present)
        aggs = result.get("aggregations")
        if aggs:
            parts.append("### Aggregations\n")
            parts.append(self._format_aggs(aggs))
            parts.append("")

        # Hits
        hits = result.get("hits", {}).get("hits", [])
        if hits:
            rows = [self._flatten_hit(h) for h in hits]
            parts.append("### Results\n")
            parts.append(self._to_markdown_table(rows))

        return "\n".join(parts) if parts else "_No results._"

    def sample_data(self, index: str, size: int = 10) -> str:
        """Get sample documents from an index."""
        safe_size = min(max(1, size), 100)
        client = self._get_client()
        result = client.search(index=index, body={"size": safe_size, "query": {"match_all": {}}})
        hits = result.get("hits", {}).get("hits", [])
        if not hits:
            return "_No documents found._"
        rows = [self._flatten_hit(h) for h in hits]
        return self._to_markdown_table(rows)

#!/usr/bin/env bash
# Daily Vista MCP usage report: parses journalctl for the previous UTC day
# and POSTs aggregate stats to the Google Apps Script webhook configured in
# ~/.vista-data-webhook.env (WEBHOOK_URL + WEBHOOK_SECRET).
#
# Triggered by vista-data-usage-report.timer at ~00:10 UTC daily.
# Mirrors percona-dk's report-mcp-usage.sh but parses "Vista MCP <tool>: <json>"
# lines and reports per-tool counts in addition to the cross-tool totals.

set -u

ENV_FILE="${ENV_FILE:-$HOME/.vista-data-webhook.env}"
if [ ! -r "$ENV_FILE" ]; then
    echo "report: $ENV_FILE not found; cannot post stats" >&2
    exit 0
fi
# shellcheck source=/dev/null
. "$ENV_FILE"

if [ -z "${WEBHOOK_URL:-}" ] || [ -z "${WEBHOOK_SECRET:-}" ]; then
    echo "report: WEBHOOK_URL or WEBHOOK_SECRET not set in $ENV_FILE" >&2
    exit 0
fi

# Date to report on. Defaults to yesterday in UTC; first arg overrides
# (used by the backfill loop). Format: YYYY-MM-DD.
DATE="${1:-$(date -u -d 'yesterday' '+%Y-%m-%d')}"
SINCE="${DATE} 00:00:00 UTC"
UNTIL="${DATE} 23:59:59 UTC"

# The MCP service runs as a systemd --user service; its stdout/stderr end up
# in the system journal, which non-root users cannot read without sudo.
# Passwordless sudo for journalctl is configured (matches percona-dk pattern).
LINES=$(sudo -n journalctl _SYSTEMD_USER_UNIT=vista-data-mcp.service \
    --since "$SINCE" --until "$UNTIL" --no-pager 2>/dev/null \
    | grep "Vista MCP " || true)

TOTAL=$(printf '%s\n' "$LINES" | grep -c "Vista MCP " || true)
TOTAL=${TOTAL:-0}

if [ "$TOTAL" -gt 0 ]; then
    PEAK=$(printf '%s\n' "$LINES" \
        | awk '{print $3}' | cut -d: -f1 \
        | sort | uniq -c | sort -rn | head -1)
    PEAK_COUNT=$(echo "$PEAK" | awk '{print $1}')
    PEAK_HOUR=$(echo "$PEAK" | awk '{print $2}')
else
    PEAK_COUNT=0
    PEAK_HOUR=0
fi

# Per-tool counts. Extract the tool name (token between "Vista MCP " and ":").
PER_TOOL_JSON="{}"
if [ "$TOTAL" -gt 0 ]; then
    PER_TOOL_JSON=$(printf '%s\n' "$LINES" \
        | sed -nE "s/.*Vista MCP ([a-zA-Z_]+):.*/\1/p" \
        | sort | uniq -c | sort -rn \
        | awk 'BEGIN{printf "{"} {printf "%s\"%s\":%d", (NR==1?"":","), $2, $1} END{printf "}"}')
fi

# Top queries (full args JSON). Group by exact arg payload.
DISTINCT=0
TOP_JSON="[]"
if [ "$TOTAL" -gt 0 ]; then
    # Extract the tool + full args body after "Vista MCP <tool>: "
    QUERIES=$(printf '%s\n' "$LINES" \
        | sed -nE "s/.*Vista MCP ([a-zA-Z_]+): (.+)$/\1 \2/p")
    DISTINCT=$(printf '%s\n' "$QUERIES" | sort -u | grep -c . || true)

    TOP_JSON=$(printf '%s\n' "$QUERIES" \
        | sort | uniq -c | sort -rn | head -20 \
        | awk '{
            count=$1; $1="";
            sub(/^ /, "", $0);
            gsub(/\\/, "\\\\", $0);
            gsub(/"/, "\\\"", $0);
            printf "%s[\"%s\",%d]", (NR==1?"":","), $0, count;
          }')
    TOP_JSON="[${TOP_JSON}]"
fi

PAYLOAD=$(cat <<EOF
{
  "secret": "${WEBHOOK_SECRET}",
  "date": "${DATE}",
  "total_calls": ${TOTAL:-0},
  "peak_hour": ${PEAK_HOUR},
  "peak_hour_count": ${PEAK_COUNT},
  "distinct_calls": ${DISTINCT:-0},
  "per_tool": ${PER_TOOL_JSON},
  "top_calls": ${TOP_JSON}
}
EOF
)

echo "report: ${DATE} total=${TOTAL} peak=${PEAK_HOUR}h(${PEAK_COUNT}) distinct=${DISTINCT}"

# Apps Script returns 302 on successful POST. Treat as success.
CODE=$(curl -sS -X POST "$WEBHOOK_URL" \
    -H "Content-Type: application/json" \
    --max-time 30 \
    -o /dev/null \
    -w "%{http_code}" \
    --data "$PAYLOAD" 2>&1) || {
    echo "report: POST failed (curl exit nonzero)" >&2
    exit 0
}

case "$CODE" in
    200|201|202|204|301|302|303|307|308)
        echo "report: posted (HTTP $CODE)"
        ;;
    *)
        echo "report: webhook returned HTTP $CODE" >&2
        exit 0
        ;;
esac

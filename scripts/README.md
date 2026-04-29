# VISTA usage analytics — deploy guide

Mirrors the percona-dk usage-report architecture. Every MCP tool call emits a
single log line; a daily systemd timer aggregates and POSTs to a Google Apps
Script webhook → Google Sheet.

## Architecture

```
mcp_server.py                     SHERPA host                Google Sheet
─────────────                  ──────────────────             ────────────
_log_tool(...)  ──systemd→  journalctl
                                   │
                                   ▼
                  vista-data-usage-report.timer (daily 00:10 UTC)
                                   │
                                   ▼
                       report-vista-usage.sh
                                   │
                                   ▼
                        webhook POST (HTTPS)  ────────────→  Apps Script doPost
                                                                 │
                                                                 ▼
                                                           Daily / TopCalls sheets
```

## What gets logged

Every `@mcp.tool()` invocation calls `_log_tool(tool_name, **args)` which emits:

```
2026-04-28 14:23:11 INFO vista_mcp Vista MCP query_clickhouse: {"sql": "SELECT ..."}
```

Full args (no truncation) per the analytics spec. For `query_clickhouse` and
`search_elasticsearch` this includes the full SQL / JSON-DSL body. **Be aware
that journalctl on SHERPA and the resulting Google Sheet will retain these
queries.** If you ever decide to trim, switch `_log_tool` to fingerprint or
truncate the value before logging.

## Sheet schema

**Daily** — one row per UTC day:

| date | total_calls | peak_hour | peak_hour_count | distinct_calls | query_clickhouse | search_elasticsearch | ch_list_databases | ... | raw_per_tool |
|---|---|---|---|---|---|---|---|---|---|

**TopCalls** — top-20 distinct (tool + args) pairs per day:

| date | tool_and_args | count |
|---|---|---|

Re-posting the same date overwrites the prior rows in both sheets.

## Deploy on SHERPA (one-time)

Assumes the `vista-data-mcp.service` systemd user-unit is already running there
and writes its logs to journalctl (matching percona-dk's setup).

1. **Create the Google Sheet + Apps Script.**
   - New blank Google Sheet titled e.g. "VISTA Usage Analytics".
   - Extensions → Apps Script → paste `apps-script.gs` content.
   - Project Settings (gear) → Script properties → add:
     `VISTA_WEBHOOK_SECRET = <generate a long random string>`
   - Deploy → New deployment → Web app:
     - Execute as: Me
     - Who has access: Anyone (with the link)
   - Copy the Web app URL.

2. **Drop the env file on SHERPA.**

   ```bash
   cat > ~/.vista-data-webhook.env <<'EOF'
   WEBHOOK_URL="<paste the Apps Script Web app URL>"
   WEBHOOK_SECRET="<paste the same random string from Script properties>"
   EOF
   chmod 600 ~/.vista-data-webhook.env
   ```

3. **Place the systemd units.**

   ```bash
   cd ~/vista-data-mcp   # or wherever the repo is checked out on SHERPA
   chmod +x scripts/report-vista-usage.sh

   mkdir -p ~/.config/systemd/user
   cp scripts/vista-data-usage-report.service ~/.config/systemd/user/
   cp scripts/vista-data-usage-report.timer   ~/.config/systemd/user/

   systemctl --user daemon-reload
   systemctl --user enable --now vista-data-usage-report.timer
   ```

4. **Verify.**

   ```bash
   systemctl --user list-timers vista-data-usage-report.timer
   ```

   You should see the next-scheduled run.

5. **Smoke-test the report manually.**

   ```bash
   ~/vista-data-mcp/scripts/report-vista-usage.sh
   # Or backfill a specific date:
   ~/vista-data-mcp/scripts/report-vista-usage.sh 2026-04-27
   ```

   Check the Google Sheet — a row for that date should appear.

## Permissions note

`report-vista-usage.sh` reads journalctl via `sudo -n journalctl ...`. SHERPA
must have passwordless sudo configured for `journalctl` for the running user
(matches percona-dk). If sudo prompts for a password the script silently exits
0; the report won't post.

## Backfill

The MCP server starts emitting log lines as soon as the new code is deployed.
If you redeploy mid-day, the daily report tomorrow will only see lines from the
redeploy onward — earlier hours of that day are missed. Acceptable for a v1.

## Privacy

- **Per-user identification: not currently captured.** SHERPA's vista-data MCP
  serves all VPN-connected Cowork clients as one anonymous identity. Adding
  per-user tracking would require an auth header in the MCP protocol — out of
  scope for this analytics rollout.
- **Query contents: full text retained** in journalctl on SHERPA and in the
  Google Sheet TopCalls tab. If sensitivity becomes an issue, switch the
  `_log_tool` body to log only the tool name + a SHA-256 fingerprint of the
  args, and log full args separately at DEBUG level (which journalctl can be
  configured to drop).

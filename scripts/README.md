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
   - Extensions → Apps Script → paste the **Apps Script source** below as the script body. Save (⌘S).
   - Project Settings (gear) → Script properties → add:
     `VISTA_WEBHOOK_SECRET = <generate a long random string>`
   - Deploy → New deployment → Web app:
     - Execute as: Me
     - Who has access: Anyone (with the link)
   - Copy the Web app URL.

   **To update later** (e.g. schema changes): paste the new code into the editor, save, then **Deploy → Manage deployments → pencil/Edit → Version: New version → Deploy.** Same Web app URL keeps working.

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

## System vs user systemd unit

On SHERPA, `vista-data-mcp.service` is a **system-level** unit (lives in
`/etc/systemd/system/`, runs as user `dennis.kittrell`). The report script
reads logs via `_SYSTEMD_UNIT=...` (system) — NOT `_SYSTEMD_USER_UNIT=...`
(which is what `percona-dk-usage-report.sh` uses, because percona-dk's MCP
runs as a `--user` service).

The aggregation timer itself (`vista-data-usage-report.timer`) is installed as
a user-level unit at `~/.config/systemd/user/` so it can run as the user
without root, calling `sudo` only for the journal read.

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

---

## Apps Script source

Paste this into your Sheet's Apps Script editor (Extensions → Apps Script).
**This README block is the canonical reference**; the live source of truth
is the script bound to the production Sheet (which may evolve via direct edits
in the editor — when you change something there, copy the new version back
into this block to keep the README honest).

Two sheets are auto-created on first run:

- **Daily** — one row per UTC day with totals + per-tool counts.
  Columns: `date | total_calls | peak_hour | peak_hour_count | distinct_calls | query_clickhouse | search_elasticsearch | ch_list_databases | ch_list_tables | ch_describe_table | ch_sample_data | es_list_indices | es_get_mapping | es_sample_data | raw_per_tool`
- **TopCalls** — top-20 distinct (tool, args) pairs per day.
  Columns: `date | tool_and_args | count`

Re-posting the same date overwrites both sheets' rows for that date, so
backfills + reruns are safe.

```javascript
/**
 * VISTA usage webhook receiver — Google Apps Script.
 *
 * Setup:
 *   1. Create a new Google Sheet ("VISTA Usage Analytics" or similar).
 *   2. Extensions → Apps Script → paste this block as the script body.
 *   3. Set Script Properties (gear → Script properties):
 *        VISTA_WEBHOOK_SECRET = <random long string, also placed in
 *                                ~/.vista-data-webhook.env on SHERPA>
 *   4. Deploy → New deployment → "Web app":
 *        - Execute as: Me
 *        - Who has access: Anyone (with the link)
 *      Copy the Web app URL → that's WEBHOOK_URL on SHERPA.
 *
 * The script is idempotent — re-posting the same date overwrites the row.
 */

const SHEET_DAILY = "Daily";
const SHEET_TOP   = "TopCalls";

const TOOL_COLUMNS = [
  "query_clickhouse",
  "search_elasticsearch",
  "ch_list_databases",
  "ch_list_tables",
  "ch_describe_table",
  "ch_sample_data",
  "es_list_indices",
  "es_get_mapping",
  "es_sample_data",
];

function doPost(e) {
  let body;
  try {
    body = JSON.parse(e.postData.contents);
  } catch (err) {
    return _resp(400, "invalid JSON");
  }

  const expected = PropertiesService.getScriptProperties().getProperty("VISTA_WEBHOOK_SECRET");
  if (!expected) return _resp(500, "secret not configured");
  if (body.secret !== expected) return _resp(403, "bad secret");

  const date = body.date;
  if (!date || !/^\d{4}-\d{2}-\d{2}$/.test(date)) return _resp(400, "missing or bad date");

  const ss = SpreadsheetApp.getActiveSpreadsheet();
  _writeDaily(ss, body);
  _writeTopCalls(ss, body);

  return _resp(200, "ok");
}

function _writeDaily(ss, body) {
  let sh = ss.getSheetByName(SHEET_DAILY);
  if (!sh) {
    sh = ss.insertSheet(SHEET_DAILY);
    const header = [
      "date", "total_calls", "peak_hour", "peak_hour_count",
      "distinct_calls", ...TOOL_COLUMNS, "raw_per_tool"
    ];
    sh.appendRow(header);
    sh.setFrozenRows(1);
    sh.getRange(1, 1, 1, header.length).setFontWeight("bold");
  }

  // Find existing row for this date; else append. Guard against empty sheet
  // (only the header row): getRange requires numRows >= 1, so we must skip the
  // lookup entirely when there are no data rows yet.
  const lastRow = sh.getLastRow();
  const dates = lastRow >= 2
    ? sh.getRange(2, 1, lastRow - 1, 1).getValues().map(r => r[0])
    : [];
  const existing = dates.findIndex(d =>
    (d instanceof Date ? Utilities.formatDate(d, "UTC", "yyyy-MM-dd") : String(d)) === body.date
  );

  const perTool = body.per_tool || {};
  const toolCounts = TOOL_COLUMNS.map(t => perTool[t] || 0);
  const row = [
    body.date,
    body.total_calls || 0,
    body.peak_hour || 0,
    body.peak_hour_count || 0,
    body.distinct_calls || 0,
    ...toolCounts,
    JSON.stringify(perTool),
  ];

  if (existing >= 0) {
    sh.getRange(existing + 2, 1, 1, row.length).setValues([row]);
  } else {
    sh.appendRow(row);
  }
}

function _writeTopCalls(ss, body) {
  let sh = ss.getSheetByName(SHEET_TOP);
  if (!sh) {
    sh = ss.insertSheet(SHEET_TOP);
    sh.appendRow(["date", "tool_and_args", "count"]);
    sh.setFrozenRows(1);
    sh.getRange(1, 1, 1, 3).setFontWeight("bold");
  }

  // Wipe prior rows for this date so re-posts replace cleanly.
  const lastRow = sh.getLastRow();
  if (lastRow > 1) {
    const dates = sh.getRange(2, 1, lastRow - 1, 1).getValues();
    const toDelete = [];
    for (let i = 0; i < dates.length; i++) {
      const v = dates[i][0];
      const ds = v instanceof Date ? Utilities.formatDate(v, "UTC", "yyyy-MM-dd") : String(v);
      if (ds === body.date) toDelete.push(i + 2);
    }
    // Delete bottom-up so row indices stay valid.
    for (let i = toDelete.length - 1; i >= 0; i--) {
      sh.deleteRow(toDelete[i]);
    }
  }

  const rows = (body.top_calls || []).map(([call, count]) => [body.date, call, count]);
  if (rows.length > 0) {
    sh.getRange(sh.getLastRow() + 1, 1, rows.length, 3).setValues(rows);
  }
}

function _resp(status, msg) {
  return ContentService
    .createTextOutput(JSON.stringify({ status, msg }))
    .setMimeType(ContentService.MimeType.JSON);
}
```

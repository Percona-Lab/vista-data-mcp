/**
 * VISTA usage webhook receiver — Google Apps Script.
 *
 * Setup:
 *   1. Create a new Google Sheet ("VISTA Usage Analytics" or similar).
 *   2. Open Extensions → Apps Script.
 *   3. Paste this file as the script body.
 *   4. Set Script Properties (gear icon → Script properties):
 *        VISTA_WEBHOOK_SECRET = <random long string, also placed in
 *                                ~/.vista-data-webhook.env on SHERPA>
 *   5. Deploy → New deployment → "Web app":
 *        - Execute as: Me
 *        - Who has access: Anyone (with the link)
 *      Copy the Web app URL → that's WEBHOOK_URL on SHERPA.
 *
 * Sheets created on first run:
 *   - "Daily" — one row per day with totals + peak hour + distinct + per-tool
 *   - "TopCalls" — one row per (date, call) pair with count
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

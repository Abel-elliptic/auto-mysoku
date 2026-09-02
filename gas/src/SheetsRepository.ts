/**
 * スプレッドシートの読み書きヘルパー。GAS側のI/Oをこのモジュールに集約し、
 * 他のモジュール（JobBatchCreator等）が直接シートAPIを呼ばないようにする。
 */

function getSheetByName(name: string): GoogleAppsScript.Spreadsheet.Sheet {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(name);
  if (!sheet) {
    throw new Error(`シートが見つかりません: ${name}`);
  }
  return sheet;
}

interface JobRowInput {
  batchId: string;
  rowId: string;
  buildingName: string;
  roomName: string;
  templateType: string;
  backgroundRef?: string;
}

function appendJobRows(rows: JobRowInput[]): void {
  const sheet = getSheetByName(SHEET_NAMES.JOB_QUEUE);
  const now = new Date().toISOString();

  const values = rows.map((row) => {
    const record: Record<string, string> = {
      batch_id: row.batchId,
      row_id: row.rowId,
      building_name: row.buildingName,
      room_name: row.roomName,
      template_type: row.templateType,
      status: "WAITING",
      created_at: now,
      claimed_at: "",
      completed_at: "",
      error_message: "",
      output_a3_ref: "",
      output_a4_ref: "",
      attempt_count: "0",
      worker_id: "",
      background_ref: row.backgroundRef || "",
    };
    return JOB_COLUMNS.map((col) => record[col] ?? "");
  });

  if (values.length === 0) return;
  sheet
    .getRange(sheet.getLastRow() + 1, 1, values.length, JOB_COLUMNS.length)
    .setValues(values);
}

/**
 * 1件だけジョブ行を追記する。コード.js（実プロジェクトの既存ファイル）の
 * updateSlideWithData() が部屋1件・テンプレート1種類ぶんの処理を終えるたびに
 * 呼び出す想定
 * （既存のバッチ処理ループの中から1行ずつ呼ばれるため、複数行をまとめて
 * 渡す appendJobRows() ではなく単発の関数を用意している）。
 */
function appendSingleJobRow(row: JobRowInput): void {
  appendJobRows([row]);
}

interface LayoutCaptureRow {
  templateType: string;
  slidePageId: string;
  elementName: string;
  elementType: string;
  xEmu: number;
  yEmu: number;
  widthEmu: number;
  heightEmu: number;
  rotationDeg: number;
  pageWidthEmu: number;
  pageHeightEmu: number;
}

function appendLayoutRows(rows: LayoutCaptureRow[]): void {
  const sheet = getSheetByName(SHEET_NAMES.LAYOUT_CAPTURE);
  const now = new Date().toISOString();
  const values = rows.map((r) => [
    r.templateType,
    r.slidePageId,
    r.elementName,
    r.elementType,
    r.xEmu,
    r.yEmu,
    r.widthEmu,
    r.heightEmu,
    r.rotationDeg,
    r.pageWidthEmu,
    r.pageHeightEmu,
    now,
  ]);
  if (values.length === 0) return;
  sheet.getRange(sheet.getLastRow() + 1, 1, values.length, values[0].length).setValues(values);
}

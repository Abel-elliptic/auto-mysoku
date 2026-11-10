/**
 * 「新規募集家賃管理」シートのG列（申し込みが可能か）が編集され、
 * チェックが外れて FALSE になった場合、該当する部屋の完成品マイソク
 * （Drive共有フォルダ内にある、一般・自社保証会社用の「マイソク_建物名部屋番号」
 * ファイル）をゴミ箱へ移動する。
 *
 * G列のチェックが外れる＝募集停止・成約済み等で、外部に共有しているこの
 * フォルダから古いマイソクを引き下げる必要があるケースを想定している。
 *
 * このファイルは他機能（マイソク作成・背景クリーンアップ等）とは独立した機能であり、
 * 個別にインストーラブルトリガー（スプレッドシートの「編集時」）を設定して使う。
 * 単純トリガー(onEdit)には依存しない（他の単純トリガーと衝突しないようにするため、
 * また確実にDrive操作の権限が認可された状態で動かすため）。
 * トリガー設定手順はdocs/runbook.md参照。
 *
 * 完成品マイソクはこのフォルダに一般(マイソク_)・自社保証会社(自社保証会社_マイソク_)
 * の2種類のみが置かれる（自社用はNASのみでここには無い）。どちらのファイル名も
 * 末尾が「マイソク_建物名部屋番号」で終わる文字列であり、このキーワードの部分一致で
 * 両方ともまとめて対象になる（ファイル名規則はpython/autohp/job_processor.pyの
 * FILENAME_PREFIXと合わせること）。
 */

const FINISHED_FLYER_DRIVE_FOLDER_ID = "1UnYAynKvhfY69EeQgqayCDKWYpFIxWX-";

const RENTAL_MANAGEMENT_SHEET_NAME = "新規募集家賃管理";
const APPLICATION_POSSIBLE_COLUMN = 7; // G列（申し込みが可能か）
const BUILDING_NAME_COLUMN = 2; // B列
const ROOM_NUMBER_COLUMN = 3; // C列

function onApplicationPossibleEdited(e: GoogleAppsScript.Events.SheetsOnEdit): void {
  const range = e.range;
  const sheet = range.getSheet();
  if (sheet.getName() !== RENTAL_MANAGEMENT_SHEET_NAME) return;
  if (range.getColumn() !== APPLICATION_POSSIBLE_COLUMN) return;

  const startRow = range.getRow();
  if (startRow === 1) return; // ヘッダー行は無視

  const numRows = range.getNumRows();
  for (let i = 0; i < numRows; i++) {
    const row = startRow + i;
    const isPossible = sheet.getRange(row, APPLICATION_POSSIBLE_COLUMN).getValue();
    if (isPossible !== false) continue; // FALSEになった行だけ処理する（チェックが入った/他の値は無視）

    const buildingName = sheet.getRange(row, BUILDING_NAME_COLUMN).getValue();
    const roomNumber = sheet.getRange(row, ROOM_NUMBER_COLUMN).getValue();
    if (!buildingName || !roomNumber) continue;

    trashFinishedFlyers(String(buildingName), String(roomNumber));
  }
}

function trashFinishedFlyers(buildingName: string, roomNumber: string): void {
  const keyword = `マイソク_${buildingName}${roomNumber}`;
  const folder = DriveApp.getFolderById(FINISHED_FLYER_DRIVE_FOLDER_ID);
  const files = folder.getFiles();
  let trashedCount = 0;
  while (files.hasNext()) {
    const file = files.next();
    if (file.getName().indexOf(keyword) !== -1) {
      file.setTrashed(true);
      trashedCount++;
    }
  }
  console.log(`${keyword}: ${trashedCount}件のファイルをゴミ箱へ移動しました。`);
}

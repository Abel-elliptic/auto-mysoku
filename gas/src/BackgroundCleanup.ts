/**
 * COMPLETED になったジョブの、一時保存の背景PNG（合成前のSlidesエクスポート画像）を
 * Driveから削除する。
 *
 * 当初はPython側（サービスアカウント）に削除させる設計だったが、この背景PNGは
 * GAS実行時のGoogleアカウント（このスプレッドシートの所有者/編集者）が作成した
 * ファイルであり、サービスアカウントは「編集者」止まりで所有者ではない。
 * Google Driveでは非所有者は完全削除(files.delete)はもちろん、ゴミ箱への移動
 * (trashed=true)についても、組織・アカウントの共有ポリシー次第では拒否される
 * ことがあり（このプロジェクトの実行アカウントは非Workspaceの個人アカウントで、
 * 実際にサービスアカウント経由の削除が403で拒否されることを確認済み）、
 * サービスアカウント側からの削除は信頼できない。
 * ファイルの所有者であるこのGASアカウント自身に削除させれば権限問題が起きない
 * ため、この関数を「時間主導型トリガー」で定期実行する運用にする
 * （設定手順は docs/runbook.md 参照）。
 */

function cleanupCompletedBackgrounds(): void {
  const sheet = getSheetByName(SHEET_NAMES.JOB_QUEUE);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return;

  const range = sheet.getRange(2, 1, lastRow - 1, JOB_COLUMNS.length);
  const values = range.getValues();

  const statusCol = JOB_COLUMNS.indexOf("status");
  const backgroundRefCol = JOB_COLUMNS.indexOf("background_ref");

  let cleanedCount = 0;
  values.forEach((row, idx) => {
    const status = row[statusCol];
    const backgroundRef = row[backgroundRefCol];
    if (status !== "COMPLETED" || !backgroundRef) return;

    try {
      const file = DriveApp.getFileById(backgroundRef);
      file.setTrashed(true);
    } catch (err) {
      // 既に削除済み（ファイルが見つからない）・手動で移動済み等は無視して次へ進む。
      console.log(`背景画像の削除をスキップ（file_id=${backgroundRef}）: ${err}`);
    }

    // 削除の成否に関わらずbackground_refは空にし、次回以降このスキャンで
    // 再度削除を試みないようにする（無駄なDrive API呼び出しを避ける）。
    sheet.getRange(idx + 2, backgroundRefCol + 1).setValue("");
    cleanedCount++;
  });

  console.log(`背景画像クリーンアップ: ${cleanedCount}件処理しました。`);
}

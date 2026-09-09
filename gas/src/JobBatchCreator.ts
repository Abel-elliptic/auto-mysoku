/**
 * 「マイソク作成」メニューのエントリーポイント。
 *
 * 「新規募集家賃管理」タブのJ列チェックボックスで選択された部屋について、
 * 自社(in_house)・一般(general)・自社保証会社(in_house_guarantee)の3種類を
 * 同一batch_idで生成する（コード.js の processNewRentals() を呼び出す。
 * 選択判定・建物別の固定値計算・文字埋め込みロジックは既存の本番運用中コードを
 * そのまま使う）。
 *
 * 「ITANDIマイソク」相当のテンプレートはまだSlidesファイルが存在しないため、
 * 今回のバッチには含めない（TEMPLATE_TYPES = ["in_house", "general", "in_house_guarantee"]）。
 */

function createFlyerBatch(): void {
  const ui = SpreadsheetApp.getUi();

  const jobSheet = getSheetByName(SHEET_NAMES.JOB_QUEUE);
  const batchId = nextBatchId(jobSheet);

  // processNewRentals()自体が「新規募集家賃管理」のJ列チェック行を読み取り、
  // 該当行ごとにupdateSlideWithData()（スライド複製・文字埋め込み・画像化・
  // ジョブ行追記）まで行う。ここではテンプレート種別ごとに1回ずつ呼び出すだけでよい。
  TEMPLATE_TYPES.forEach((templateType) => {
    processNewRentals(templateType, batchId);
  });

  ui.alert(`マイソク作成ジョブを登録しました。\nバッチID: ${batchId}`);
}

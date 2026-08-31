/**
 * スプレッドシートを開いたときにカスタムメニューを追加する。
 */
function onOpen(): void {
  SpreadsheetApp.getUi()
    .createMenu("マイソク")
    .addItem("マイソク作成", "createFlyerBatch")
    .addItem("レイアウト情報取得", "captureLayoutFromActivePresentation")
    .addToUi();
}

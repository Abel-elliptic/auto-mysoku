/**
 * GCPプロジェクトをデフォルトから標準プロジェクトへ切り替えた直後、
 * 既存の認可(OAuth)がリセットされることへの対策。
 *
 * 使い方: GCPプロジェクトを切り替えた直後に、Apps Scriptエディタの関数選択
 * ドロップダウンから本関数を選び、手動で一度だけ実行する。認可ダイアログが
 * 出たら「許可」をクリックする。これにより、このプロジェクトが使う全スコープを
 * 一度の承認でまとめて再認可でき、reminder.js等の時間主導トリガーが
 * 承認待ちのまま個別に失敗するのを避けられる。
 *
 * 本番データを書き換える処理は一切含まない(すべて読み取り専用の呼び出し)。
 */
function reauthorizeAllScopes(): void {
  // Sheets: このプロジェクトが紐づくスプレッドシートを開くだけ
  SpreadsheetApp.getActiveSpreadsheet().getName();

  // Slides: 自社向けテンプレートを開くだけ(編集はしない)
  SlidesApp.openById("1QB2132Hz0XMREBKmxddQTp-9S34dijgy2oUeBODyVtM").getName();

  // Drive: ルートフォルダの名前を読むだけ
  DriveApp.getRootFolder().getName();

  // Mail: 送信はせず、残り送信可能数を確認するだけ
  MailApp.getRemainingDailyQuota();

  // 外部HTTP(UrlFetchApp): autoUpdateHP.jsが使うスコープを、無関係な安全なURLへの
  // アクセスで代わりに発火させる(実際のWordPress同期エンドポイントには一切触れない)
  UrlFetchApp.fetch("https://www.google.com", { muteHttpExceptions: true });

  // トリガー(ScriptApp): reminder.js/updateSParking.jsの時間主導トリガーが使うスコープ
  ScriptApp.getProjectTriggers();

  // LockService: このリポジトリのIdGenerator.tsが採番の排他制御に使うスコープ
  LockService.getScriptLock();

  SpreadsheetApp.getUi().alert(
    "再認可用のスコープをすべて実行しました。認可ダイアログが出た場合は「許可」をクリックしてください。"
  );
}

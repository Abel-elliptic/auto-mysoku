# 運用手順（ドラフト）

本ドキュメントは初期実装時点でのドラフトであり、実運用に入る前に
要確認事項（`architecture.md` 参照）をすべて解消した上で更新すること。

## 初期セットアップ

### GAS側

1. 実際に運用中のスプレッドシート（ID: `1BPLLSSIM37C7aA-zuQydf_RkyFxA9wEfz_Yix2mixk0`、
   `新規募集家賃管理`等の既存タブを持つもの）に、`docs/sheets_schema.md` に従って
   「ジョブ管理」「レイアウト情報」の2タブを追加する（既存タブは変更しない）。
2. `gas/` をこのスプレッドシートに `clasp` で紐付け、`.clasp.json.example` を参考に
   `.clasp.json` を作成する。
3. `clasp clone <scriptId>` で既存プロジェクトをバックアップし、既存ファイル
   （コード.js・const.js・reminder.js・updateSParking.js・autoUpdateHP.js）を
   `gas/src/` へコピーする。`コード.js`へ`docs/architecture.md`記載の最小限の変更を
   適用する（詳細は同ドキュメント「既存Apps Scriptプロジェクトとの共存について」参照）。
4. `appsscript.json` の Slides API / Drive API（高度なサービス）が有効になっていることを確認する。
5. Script Properties に `BACKGROUND_DRIVE_FOLDER_ID` を設定する
   （SlidesファイルIDは`templates/*.yaml`に実IDとして直接記載済みのため、
   Script Propertiesでの設定は不要）。
6. `npm run push` でデプロイする（`clasp`v3は`.ts`を自動変換しないため、
   `tsc`でのビルドを挟んでから`clasp push`するnpmスクリプトを使う）。
   スプレッドシートを開いて「マイソク」メニューが表示されることを確認する。
7. 一時保存の背景PNGクリーンアップ用トリガーを設定する: Apps Scriptエディタの
   左メニュー「トリガー」→「トリガーを追加」で、関数
   `cleanupCompletedBackgrounds`・イベントのソース「時間主導型」・
   種類「分ベースのタイマー」・間隔「10分おき」（任意の間隔でよい）を選択して保存する。
   （この削除処理は所有者であるこのGoogleアカウント自身が行う必要があるため、
   Python側のサービスアカウントではなくGAS側のトリガーで実行する設計。
   詳細はコード内コメント参照）。

### 社内PC側

1. Python 3.11+ をインストールし、`python/` で `pip install -e ".[dev]"`。
2. サービスアカウント鍵ファイルを、リポジトリ管理外の安全な場所に配置する。
3. `.env.example` を `.env` にコピーし、実際の値を設定する。
4. NAS専用アカウントを作成し、`募集用`（読取専用）・`マイソク`系出力先（読書き）の
   権限のみを付与する（`docs/security.md` 参照）。
5. `python -m autohp.job_poller` でポーラーを起動する（常駐サービス化は要検討）。

## 日常運用

1. スプレッドシートの「新規募集家賃管理」で対象部屋のJ列（選択チェックボックス）に
   チェックを入れる。
2. 「マイソク」メニュー →「マイソク作成」を実行する。
3. 「ジョブ管理」タブで各行のstatusがCOMPLETEDになることを確認する。
4. ERRORになった行は `error_message` を確認し、原因（画像欠損等）に応じて
   NAS上の画像を補完してから再度「マイソク作成」を実行する。

## 障害対応

- **PROCESSINGのまま進まない行がある**: ワーカークラッシュの可能性。
  `stale_processing_minutes` 経過後、自動的に再クレーム対象になる。
  即座に再実行したい場合は該当行の `status` を手動で `WAITING` に戻す。
- **NAS接続エラーが継続する**: NAS/ネットワークの疎通を確認する。
  `max_retry_attempts` を超えるとERRORへ自動遷移する。
- **必須画像欠損でERRORになる行が多い**: NAS上の画像ファイル名が
  テンプレート設定（`templates/*.yaml` の `source_filename`）と一致しているか確認する。
- 詳細なエラー内容はスプレッドシートには出さない方針のため、社内PCのログ
  （`LOG_DIR/autohp.log`）を確認すること。

## 未確定事項

本ドラフトは多くの運用パラメータに仮値を使っている
（ポーリング間隔・リトライ回数・ログ保持日数等）。
本番投入前に `docs/architecture.md` の「要確認事項一覧」をすべて関係者と確認すること。

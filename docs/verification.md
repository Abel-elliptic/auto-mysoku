# システム動作確認手順

初回導入時・実装変更時に、GAS/Python/NASを実際に動かして一通り正しく動作することを
確認するための手順書。日常運用・障害対応は [`runbook.md`](runbook.md) を参照。

専門用語の説明や画面操作まで含めた、非エンジニア向けのより丁寧な手順は
[`verification_beginner.md`](verification_beginner.md) を参照。本ドキュメントは
その要点をコマンド中心に凝縮したエンジニア向け版。

各項目はチェックボックスで進捗を管理する。手順の実行結果は末尾の「結果記録」に記入する。

> **重要**: 本システムは実際に本番運用中のスプレッドシート・GASプロジェクトと
> 統合している。そのプロジェクトにはこのシステムと無関係な本番機能
> （退去リマインドメール・駐車場空き状況更新・外部サイトへのデータ同期等）も
> 含まれるため、`clasp push`前には必ず`clasp clone`でバックアップを取ること。
> テスト目的で実データを誤って書き換えないよう、「マイソク作成」の実行前には
> 対象行がテスト専用の行であることも必ず確認すること。詳細は
> [`architecture.md`](architecture.md)「既存Apps Scriptプロジェクトとの共存について」を参照。

## 0. 前提条件チェックリスト

- [ ] `.env` を作成し、`GOOGLE_SERVICE_ACCOUNT_JSON_PATH` / `SPREADSHEET_ID`
      （実スプレッドシートID: `1BPLLSSIM37C7aA-zuQydf_RkyFxA9wEfz_Yix2mixk0`）/
      `SMB_*` 等を設定済み
- [ ] 対象スプレッドシートに「ジョブ管理」「レイアウト情報」の2タブを新規作成済み
      （既存の`新規募集家賃管理`・`ITANDI`・`入退去管理`・`駐車場価格設定`タブは
      変更不要。列定義は [`sheets_schema.md`](sheets_schema.md) 参照）
- [ ] 既存Apps Scriptプロジェクトを`clasp clone`でバックアップ済み、その既存ファイル
      （コード.js・const.js・reminder.js・updateSParking.js・autoUpdateHP.js）を
      ローカルの`gas/src/`へコピー済み、`コード.js`へ`docs/architecture.md`記載の
      最小限の変更を適用済み
- [ ] `.clasp.json`のscriptIdを実プロジェクトのIDに設定し、`clasp push` 済み
- [ ] Script Properties に `BACKGROUND_DRIVE_FOLDER_ID` を設定済み
      （`SLIDES_TEMPLATE_FILE_ID_*` は現在 `templates/*.yaml` 内に実IDを直接記載しており
      GAS側では未使用 — コード.js側が実IDをハードコードで参照する）
- [ ] `新規募集家賃管理` タブに、テスト用に安全に使える行が用意されている
      （実データを誤って上書きしないこと）
- [ ] テスト用NAS共有（または検証用SMBサーバ）が用意されている
      （現時点では写真の配置座標が未確定のため、この手順では写真合成の確認は
      限定的になる。下記「3. Python側の手動確認」の注記を参照）

## 1. 自動テストの実行確認

- [ ] Python:
  ```bash
  cd python && pip install -e ".[dev]" && ruff check . && pytest -q
  ```
  → `25 passed`、ruffが `All checks passed!` になることを確認
- [ ] GAS:
  ```bash
  cd gas && npm install && npm run typecheck && npm run build
  ```
  → typecheckはエラー0件（出力なし）、buildは`src/*.js`が生成されて終了することを確認

## 2. GAS側の手動確認

- [ ] スプレッドシートを開き、「マイソク」メニューに「マイソク作成」「レイアウト情報取得」が
      表示されることを確認
- [ ] `新規募集家賃管理` タブのテスト用行の J列（選択チェックボックス）にチェックを入れ、
      「マイソク作成」を実行
- [ ] 成功アラートに「バッチID: JOB-YYYYMMDD-NNNN」が表示されることを確認
- [ ] 「ジョブ管理」タブに、同一 `batch_id` で `template_type` が `in_house` / `general` の
      2行が `status=WAITING` で追加されていることを確認（`building_name` / `room_name` が
      正しく入っていること、`background_ref` にDriveファイルIDが入っていることも確認）
- [ ] Driveの`BACKGROUND_DRIVE_FOLDER_ID`フォルダに、文字情報が焼き込まれたスライドの
      PNG画像が2枚（in_house用・general用）生成されていることを確認。**この時点で
      画像を開き、賃料・住所等の文字が実際に印刷して読めるレベルの鮮明さかを
      目視確認すること**（Slidesサムネイルの解像度上限リスクが顕在化しやすい箇所。
      `architecture.md`「Google Slides背景生成の技術的制約」参照）
- [ ] Apps Scriptの実行ログ（拡張機能→Apps Script→実行数）に
      `Slidesサムネイル実測サイズ: width=...px, height=...px` が出力されていることを確認し、
      実測値を`architecture.md`の該当節に追記する
- [ ] （写真配置座標を確定させる作業を行う場合）対象Slidesファイルに仮画像を配置した状態で
      「レイアウト情報取得」を実行し、プロンプトにテンプレート種別とファイルIDを入力 →
      「レイアウト情報」タブに x_emu / y_emu / width_emu / height_emu / rotation_deg 等が
      出力されることを確認（手順は`template_config_spec.md`「座標の決め方」参照）

## 3. Python側の手動確認（ポーラー単体）

> **注記**: `templates/in_house.yaml` / `templates/general.yaml` は現時点で
> 写真配置座標（`image_slots`）が未確定のため、`background`（Slidesエクスポート
> 画像そのもの）以外の合成は行われない。つまりこの手順で確認できるのは
> 「Slidesで作った画像がそのままA3/A4サイズでNASへ出力されること」までで、
> 写真の合成確認はできない（座標確定後に別途確認すること）。

- [ ] `python -m autohp.job_poller` を起動し、`LOG_DIR/autohp.log` に `poller_start`
      ログが出力されることを確認
- [ ] 手順2で作成したWAITING行が、数十秒以内に `PROCESSING` → `COMPLETED` へ遷移することを
      「ジョブ管理」タブで確認（`claimed_at` / `completed_at` / `worker_id` が埋まる）
- [ ] `output_a3_ref` ・ `output_a4_ref` にNAS相対パスが書き込まれ、NAS出力先
      （`自社マイソク/{建物名}/{部屋番号}/{date}_A3.jpg` 等、`in_house`は`自社マイソク`、
      `general`は`マイソク`フォルダ）に実際にJPEGが生成されていることを確認
- [ ] 生成されたJPEGの寸法をPillow等で確認し、A3が4961×3508px、A4が3508×2480px
      （±1px許容）になっていることを確認
  ```python
  from PIL import Image
  print(Image.open("〈出力ファイルパス〉").size)
  ```
- [ ] 画像を目視し、GASで焼き込んだ文字（賃料・住所等）が正しく表示され、
      印刷解像度で読めるレベルの鮮明さであることを再確認する

## 4. 異常系の確認

- [ ] ポーラー起動中にNAS（またはSMBサーバ）を一時的に切断し、対象ジョブが `WAITING` へ
      差し戻され `attempt_count` が増加することを確認。`max_retry_attempts`（既定3回）を
      超えたら `ERROR`（「一時的な処理エラーが複数回発生しました。管理者に確認してください。」）
      に昇格することを確認
- [ ] `新規募集家賃管理` の建物名に `../../etc` のような不正文字列を含むテスト行を
      作成して実行し、該当ジョブが `ERROR` になり、かつログに `PathSafetyError` が
      記録されている一方でNASへの実際のファイルアクセスが発生していないこと（ログの
      `stage` で確認。この経路は出力パス生成時に必ず通るため、写真スロットが
      未設定の現状でも確認可能）
- [ ] 必須画像欠損時のERROR化は、現状 `required_images` が空（写真スロット未設定）のため
      確認できない。写真配置座標を確定させ`required_images`に実際のスロットを追加した後、
      該当画像をNASから一時的に除いた状態で「マイソク作成」を実行し、ジョブが`ERROR`に
      なること・`error_message`に内部パスが含まれないことを確認すること

## 5. セキュリティ観点のセルフチェック

- [ ] ポーラー稼働中の社内PCで `netstat -an`（または `ss -tlnp`）を実行し、待受（LISTEN）
      ポートが増えていないことを確認
- [ ] `git status` で `.env` ・サービスアカウント鍵ファイルが追跡対象に入っていないことを
      確認（`.gitignore` に含まれていることも合わせて確認）
- [ ] NASアカウントの権限が「募集用」（読取専用）・出力先（読書き）のみに限定されていることを、
      NAS管理画面上で確認

## 結果記録

| 手順番号 | 実行日 | 実行者 | 結果(OK/NG) | 備考 |
|---|---|---|---|---|
| | | | | |

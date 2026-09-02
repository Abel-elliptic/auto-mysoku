# アーキテクチャ設計

## 目的

Canvaで手作業作成している賃貸マイソクを、GAS起点で自動生成する。ユーザーが
スプレッドシート上で部屋を選択し「マイソク作成」を実行すると、自社マイソク・
一般マイソクの2種類 × 選択部屋数の画像が自動生成され、NASに保存される
（ITANDIマイソクは将来追加予定。詳細は本ドキュメント末尾の要確認事項3を参照）。

## 実在のスプレッドシート・GASコードとの統合について

本システムは当初、リポジトリが空だったため「物件マスタ」「文字情報のSlides埋め込み」を
含めすべて新規構築する前提で設計されていた。しかし実際には、以下がすでに本番運用中の
実データ・実コードとして存在することが判明したため、それらをそのまま再利用する方針に
設計変更している。

- **実スプレッドシート**（ID: `1BPLLSSIM37C7aA-zuQydf_RkyFxA9wEfz_Yix2mixk0`）の
  既存タブをそのまま使う。新規に「物件マスタ」タブを作ることはしない
  - `新規募集家賃管理`: 部屋一覧・J列の選択チェックボックス（今回の「選択」列として流用）
  - `ITANDI`: 所在地・専有面積・間取り・備考・バイク置場・駐輪場のデータソース
    （出力テンプレートではなく入力データ源。紛らわしいがITANDIマイソクとは別物）
  - `入退去管理`: 入居可能日の算出に使用
  - `駐車場価格設定`: 建物別の駐車場料金マスタ
- **既存GAS**の `processNewRentals()` / `updateSlideWithData()` /
  `getBuildingInfo()` / `formatCurrency()` をそのまま再利用する。これらは建物ごとの
  固定値・料金計算ロジックを含む本番運用中のコードであり、値や条件分岐は一切
  変更しない。`updateSlideWithData()` は、建物名・賃料・住所などの**文字情報をすべて
  Slides側に`replaceAllText()`で焼き込んでから**スライドを完成させる
  （これは新設計の重要な前提であり、下記「Google Slides背景生成」節を参照）。
- 自社向け（`is_own=true`）と一般/仲介向け（`is_own=false`）で、Slidesファイルが
  2種類切り替わる（`1QB2132Hz0XMREBKmxddQTp-9S34dijgy2oUeBODyVtM` /
  `1rr3v0UMjSqMDJPjAvBveoqnj7r210nllVgyTxO22jOc`）。これがそのまま
  `template_type: in_house / general` に対応する。

## 既存Apps Scriptプロジェクトとの共存について（重要）

実際のApps Scriptプロジェクト（スクリプトID: `1Ro2f7wv5cDPHDOq6USghMcURL1iq64q1Ay6QJSyI4yKb7wWctRVOqAuf`、
要確認: 正確性は運用担当者側で必ず再確認すること）には、`processNewRentals()`等を含む
`コード.js`のほかに、以下の本番運用中ファイルが存在することが判明した（2026-08時点で確認）。

| ファイル | 内容 |
|---|---|
| `コード.js` | マイソク関連関数に加え、物件データ・駐車場データのWordPress/DB同期用SQL生成、PDF出力、チェックボックスリセット等、マイソクと無関係な多数の関数を含む |
| `const.js` | リマインドメール用の設定・宛先・文面テンプレート |
| `reminder.js` | 退去予定日の3営業日前に担当者へメール通知するバッチ処理（時間主導型トリガーで毎日実行） |
| `updateSParking.js` | 別のSlides（駐車場空き状況掲示用、ID: `1qCo4xoKpgEeOWPP5sxkLWLw53dEp5zAEkHbAOblPsaw`）を更新する処理 |
| `autoUpdateHP.js` | 物件・駐車場データを外部WordPressサイトへAPI経由で同期する処理（**APIキーを含む**） |

**このリポジトリの`gas/src/`には、上記の既存ファイルを一切含めない。** 理由:
1. `autoUpdateHP.js`に本番のAPIキーが直書きされており、Gitリポジトリにコミットすると
   意図せず外部（GitHub等）へ漏えいするリスクがある
2. リマインドメール・DB同期など、このシステムと無関係な本番機能を万が一
   間違って上書き・削除してしまうリスクを避けるため
3. `clasp push`は、ローカルのプロジェクトフォルダの中身で**リモートのファイル一覧を
   まるごと置き換える**ため、ローカルに無いファイルはリモートからも消える

そのため運用フローは以下のようになる（`docs/verification_beginner.md`にも
同様の手順を記載）:

1. `clasp clone <scriptId>` で既存プロジェクトを一旦別フォルダにバックアップする
2. バックアップした`コード.js`・`const.js`・`reminder.js`・`updateSParking.js`・
   `autoUpdateHP.js`を、このリポジトリの`gas/src/`へコピーする
   （`.gitignore`で除外設定済みなので誤ってコミットされない）
3. `コード.js`にのみ、以下の最小限の変更を手作業で加える（他の関数・他のファイルは
   一切変更しない）:
   - `function processNewRentals(is_own = false) {` を
     `function processNewRentals(is_own = false, batchId) {` に変更
   - 関数末尾付近の `updateSlideWithData(rowData, is_own);` を
     `updateSlideWithData(rowData, is_own, batchId);` に変更
   - `function updateSlideWithData(rowData, is_own) {` を
     `function updateSlideWithData(rowData, is_own, batchId) {` に変更
   - `updateSlideWithData()`内の`replaceAllText`ループの直後（関数の一番最後、
     閉じ括弧の直前）に以下を追加:
     ```js
     // ここから新規追加: 画像化してDriveへ保存し、ジョブ管理シートへ1行追記する。
     if (!batchId) return;

     const driveFileId = exportSlidePageAsImage(presentation.getId(), newSlide.getObjectId());
     const templateType = is_own ? "in_house" : "general";
     appendSingleJobRow({
       batchId: batchId,
       rowId: batchId + "-" + templateType + "-" + rowData.buildingName + "-" + rowData.roomNumber,
       buildingName: rowData.buildingName,
       roomName: String(rowData.roomNumber),
       templateType: templateType,
       backgroundRef: driveFileId,
     });
     ```
   - `processNewRentalsForOwn()`はそのまま変更不要（`batchId`未指定＝`undefined`で
     呼ばれるため、`updateSlideWithData`側の`if (!batchId) return;`によりジョブ管理への
     書き込みは行われず、従来どおりスライド作成のみで終わる＝後方互換）
4. `.clasp.json`の`scriptId`を実際のIDに設定し、`clasp push`する

この手順により、`exportSlidePageAsImage()`・`appendSingleJobRow()`（このリポジトリの
`SlidesBackgroundGenerator.ts`・`SheetsRepository.ts`で定義）が、コピーした`コード.js`
から呼び出せるようになる（Apps Scriptは同一プロジェクト内の全ファイルがひとつの
グローバルスコープを共有するため、ファイルを分けても関数はどこからでも呼べる）。

## 全体フロー

```
[人] 「新規募集家賃管理」タブでJ列にチェック → 「マイソク作成」メニュー実行
        ↓
[GAS] createFlyerBatch() が batch_id を1つ発行し、
        processNewRentals(is_own=false/true, batchId) を2回呼ぶ
        → 各呼び出しがチェック済み行ごとに updateSlideWithData() を実行:
          Slidesを複製・文字情報をreplaceAllTextで焼き込み
          → getThumbnailで画像化 → Driveへ保存
          → ジョブ管理シートへ1行(WAITING)追記（background_refにDriveファイルID）
        ↓ （GASの処理はここで終了。写真の合成は行わない）
[社内PC / Python] 定期ポーリングでWAITING行を検出
        → 該当行をPROCESSINGへクレーム（楽観的ロック）
        → NASから部屋写真をSMB取得、Driveから背景（文字焼き込み済み）画像を取得
        → templates/*.yaml の座標定義に従って写真を合成 → A3画像 → A4画像(縮小生成)
        → NASの出力先へ書き込み
        → シートへCOMPLETED/ERRORを報告
```

## 採用したジョブ引き渡し方式（案A〜Dの比較と選定）

| 案 | 概要 | ポート開放 | 外部公開 | 実装難易度 | 保守性 | 備考 |
|---|---|---|---|---|---|---|
| A: GAS→外部HTTP API→社内PC | 社内PCがAPIサーバーを立てる | 必要 | 社内PCを公開 | 中 | 中 | セキュリティ要件に反するため不採用 |
| B: GAS→Cloudflare Tunnel→社内PC | トンネル経由で外部から接続 | 不要だが実質的に受信経路を開く | 限定的だが受信経路あり | 中 | 中 | 「外部から社内へ接続」を避けたい方針に反するため不採用 |
| C: GAS→Drive にジョブ書き込み | JSON等をDriveフォルダへ | 不要 | なし | 低〜中 | 中（進捗の可視化に追加実装が要る） | 大きいバイナリの受け渡しには適する |
| **D: GAS→Sheets にジョブ書き込み（採用）** | ジョブ管理シートの行として管理 | 不要 | なし | 低 | 高（人の目で進捗を確認できる） | 状態管理の主軸として採用 |

**採用構成: D（Sheets）を主軸、C（Drive）を大きいバイナリ（Slides背景PNG）の
受け渡しに併用するハイブリッド。** 社内PCはGoogle APIへのアウトバウンド
HTTPS通信とNASへのSMB通信のみを行い、待受ポートは一切開かない。

## セキュリティ（最重要要件）

- ルーターのポート開放なし、NAS・社内PCのインターネット公開なし。
- 社内PC → Google API / NAS への発信のみで完結（受信経路なし）。
- 認証情報はすべて環境変数/OS資格情報ストア経由（ハードコード禁止）。
- パストラバーサル対策: `python/autohp/path_safety.py` が唯一の窓口。
  ホワイトリスト正規表現でのセグメント検証 → 正規化 → 許可ルート配下の
  プレフィックス境界チェックを行う。NASクライアント（`smb_client.py`）は
  検証済みの `SafePath` 型のみを受け取り、生の文字列パスを受け付けない。
- 最小権限のNAS専用アカウント（`募集用`読取専用・`マイソク`出力先読書きのみ）。
- OSコマンド実行・eval等の任意コード実行経路を作らない。
- 処理ログは構造化ログとしてローカルファイルへ出力し、内部パス・認証情報・
  スタックトレースはスプレッドシートへは一切書き戻さない
  （定型の日本語メッセージのみ）。

詳細は [`security.md`](security.md) を参照。

## A3/A4 出力仕様

- A3(420×297mm)@300dpi ≈ **4961×3508px**、A4(297×210mm)@300dpi ≈ **3508×2480px**。
- ISO 216のA系列は全サイズで縦横比（√2:1）が共通のため、A3合成後の画像を
  縦横とも **1/√2倍** に縮小するだけでA4画像を厳密に導出できる
  （テンプレート側にA4専用座標を持たせる必要はない）。
- 出力形式は高解像度JPEGのみ（PDF併用なし・ユーザー確定事項）。

## Google Slides背景生成の技術的制約（重要・リスク格上げ）

Slides APIの `Presentations.Pages.getThumbnail` はページを画像化する公式手段だが、
`thumbnailProperties.thumbnailSize` の解像度には上限があり、A3印刷解像度
（長辺約4961px）に対して不足する可能性が高い。**正確な上限ピクセル数は
断定せず**、`SlidesBackgroundGenerator.ts` の `exportSlidePageAsImage()` が
実際に取得したサムネイル画像のピクセル寸法を取得のたびにログ出力する運用とし
（Google側の仕様変更にも追従しやすくするため）、実測値が判明し次第この節へ追記する。

**背景は「部屋ごとに動的」（実データを反映）であり、かつ文字は完全にSlides側で
焼き込み済みである。** 実際に統合した既存GAS（`RentalDataLookup.ts`の
`updateSlideWithData()`）は、建物名・賃料・住所・間取り等の実際に読める必要が
ある文字情報を`replaceAllText()`でSlidesページに直接埋め込んでから
`getThumbnail`でエクスポートする。これは当初この節で想定していた
「背景はテンプレート固定・文字はPython側で高解像度描画」という設計とは異なり、
**印刷物として読む文字そのものの鮮明さが、Slidesサムネイルの解像度上限に
直接依存する**ことを意味する。以前の設計ではこのリスクを「背景デザインが
多少粗くても写真と文字はPython側で高精細に描く」ことで許容していたが、
今回の統合によりリスクの深刻度が上がっている。

このリスクへの対応（現時点の方針）:

- 短期: `docs/verification.md`のとおり、初回のエンドツーエンド確認で
  実際に生成された画像の文字が印刷解像度で読めるレベルかを重点的に目視確認する。
  ログに出力される実測サムネイルサイズ（px）も必ず記録する。
- 文字が不鮮明だった場合の対応案（要検討・未実装）: (a) `getThumbnail`が
  返す最大サイズより大きい解像度を得る代替手段がないか調査する、
  (b) Slidesページ自体を大きいサイズで作成し縮小せず使う、
  (c) 文字だけは結局Python側で重ねて高解像度描画し直す設計へ戻す
  （その場合`replaceAllText`で埋め込んだ文字と重複しないよう、Slidesテンプレート側の
  該当プレースホルダーを空文字にする調整が必要）。

## ジョブ状態管理

`WAITING → PROCESSING → COMPLETED / ERROR` の4状態。バッチ単位で
`JOB-YYYYMMDD-NNNN` を発行し（`gas/src/IdGenerator.ts`、`LockService`で採番を排他制御）、
行単位（部屋×テンプレート）で成功/失敗を追跡する。

- クレームは「該当行のみ再読込→PROCESSING書込→再読込で確認」という楽観的ロック
  （`python/autohp/sheets_client.py: claim_job`）。Sheets APIにCAS相当のプリミティブが
  ないため完全な排他ではないが、**ポーラーは単一PCでのみ稼働させる運用を暫定の
  正式方針とする**（小規模事業所での想定稼働台数・処理量であれば十分であり、
  楽観的クレームで事実上の二重処理リスクは無視できるレベルに抑えられるため）。
  複数PCを同時稼働させたい場合は、その時点で真の排他制御を再検討する。
- `TransientError`（NAS一時切断等）→ WAITINGへ差し戻し、リトライ上限超過でERROR
  （デフォルト: リトライ3回。`python/autohp/config.py` の `max_retry_attempts`）。
- `PermanentError`（必須画像欠損等）→ 即ERROR、リトライしない。
- `claimed_at` から一定時間経過したPROCESSING行は放棄されたとみなし再取得対象にする
  （ワーカークラッシュ対策。デフォルト: 10分、`stale_processing_minutes`）。

## 実装マイルストーン

1. リポジトリ/CI雛形
2. Sheetsスキーマ + GASバッチ作成（Slidesはスタブ）
3. Pythonポーラー + in_houseテンプレートのみ、テキストのみ合成
4. SMB連携・path_safety・実画像合成・必須画像欠損時ERROR
5. Slides背景生成方式の確定 + 実装
6. 残り2テンプレート追加 + A4縮小生成
7. リトライ・放棄ジョブ回収・ログ整備
8. セキュリティ強化（最小権限アカウント切替）+ ドキュメント整備

## 要確認事項一覧と暫定決定（推奨値）

ビジネス固有の事実（列名・NAS実機情報等）は推測せず、以下は「実データ確認後に
差し替える前提の暫定決定・推奨デフォルト」として明記する。①②はビジネス側の
実データ確認が必須で保留のまま、③〜⑩はこのリポジトリ内で決定済みの推奨値として運用する。

1. **物件マスタの完全な列一覧**: **解消**。「物件マスタ」という新規タブは作らず、
   実在する`新規募集家賃管理`・`ITANDI`・`入退去管理`・`駐車場価格設定`の4タブを
   `gas/src/RentalDataLookup.ts`がそのまま参照する（列一覧は同ファイルのコメント参照）。
2. **実際のNASプラットフォーム・共有名・認証情報**: 保留（実機確認必須）。
   `smbprotocol`はSMB2/3対応でSynology/QNAP/Windows Serverいずれにも通用するため、
   `smb_client.py`自体の変更は不要。実機確定後は`.env`の値のみ設定すればよい。
3. **ポーリング間隔・リトライ回数上限・放棄PROCESSING判定時間・ログ保持日数**:
   実装済みのデフォルト値（30秒間隔・リトライ3回・放棄判定10分・ログ30日保持、
   `python/autohp/config.py`）を正式デフォルトとして採用。運用開始後に実測して調整する。
4. **建物名・部屋番号に許容する文字種**: 実装済みの許可セット（英数字・漢字/かな/
   カナ・一部の全角記号・空白・ハイフン・アンダースコア・ドット、
   `python/autohp/path_safety.py`）を暫定の正式仕様として採用。実データで弾かれる
   ケースが出た場合のみ許可文字を追加する。
5. **背景がテンプレート固定か部屋ごとに動的か**: **解消（想定と逆の結果）**。
   実際には部屋ごとに動的（実データの文字がSlidesに焼き込まれる）。
   上記「Google Slides背景生成の技術的制約」節で詳細とリスクを説明している。
6. **A3/A4出力ファイルの命名規則**: `{date}_A3.jpg` / `{date}_A4.jpg` を正式仕様として採用。
7. **既存のSlides背景生成GASが実在するか**: **解消（想定と逆の結果）**。
   実在した。`gas/src/RentalDataLookup.ts`として移植・統合済み
   （詳細は本ドキュメント冒頭「実在のスプレッドシート・GASコードとの統合について」参照）。
8. **Slides `getThumbnail` の正確な最大解像度定数**: 断定せず、実測ログ出力で対応
   （`gas/src/SlidesBackgroundGenerator.ts`にログ追加済み）。今回の統合で
   このリスクの深刻度が上がっているため、初回動作確認で最優先に確認すること。
9. **社内PCのOS種別**: 断定不可だが、`keyring`パッケージ（Windows/macOS/Linux
   いずれにも対応）でOS資格情報ストアを抽象化する方針を採用し、OS確定前でも
   実装を進められるようにする（`docs/security.md`参照）。
10. **複数PCでポーラーを同時稼働させる可能性**: **単一PCでのみ稼働させる運用を
    正式方針とする**（上記「ジョブ状態管理」節を参照）。
11. **ITANDIマイソクに相当する第3のテンプレート**: 保留（今は未整備）。
    ユーザー確認済み: 自社(in_house)・一般(general)の2種類のSlidesファイルのみが
    実在し、ITANDI向けの専用テンプレートはまだ作成されていない。
    `templates/itandi.yaml`にプレースホルダーとして残しているが、
    `gas/src/Config.ts`の`TEMPLATE_TYPES`には含めておらず、「マイソク作成」実行時に
    このテンプレートのジョブが作られることはない。将来追加する場合の手順は
    `templates/itandi.yaml`のコメントを参照。
12. **写真（living.jpg等）の配置座標**: 未確定（保留）。実際のSlidesファイルに
    仮画像を配置し「レイアウト情報取得」で座標を取得する必要がある。
    詳細な手順は`docs/template_config_spec.md`「座標の決め方」を参照。
    座標が確定するまで、`templates/in_house.yaml`・`templates/general.yaml`の
    `image_slots`は背景（Slidesエクスポート画像）のみで、写真の合成は行われない。

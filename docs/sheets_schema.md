# スプレッドシートスキーマ

実スプレッドシート（ID: `1BPLLSSIM37C7aA-zuQydf_RkyFxA9wEfz_Yix2mixk0`）の
既存タブ4つ（募集データ入力用、変更しない）に、新規タブ2つ（ジョブ管理用）を追加した
構成。タブ名は `gas/src/Config.ts` の `SHEET_NAMES` と一致させること。

## 既存タブ（変更しない・そのまま参照する）

「物件マスタ」のような新規タブは作らず、実データが入っている以下の4タブを
既存のコード.js（実プロジェクトのファイル、このリポジトリには含まれない。
docs/architecture.md「既存Apps Scriptプロジェクトとの共存について」参照）が
そのまま読む。列レイアウトは実データに合わせて既存のまま（このドキュメントの
ために列を作り替えたりしない）。

### `新規募集家賃管理` (`SHEET_NAMES.RENTAL_MANAGEMENT`)

マイソク作成の選択トリガー。列インデックス（0始まり）はコード.js内の
コメントに準拠。

| 列 | 項目 |
|---|---|
| B (index 1) | 建物名 |
| C (index 2) | 部屋番号 |
| D (index 3) | 家賃 |
| E (index 4) | 管理費 |
| H (index 7) | 敷金 |
| I (index 8) | 礼金 |
| J (index 9) | 選択チェックボックス（`true`でマイソク作成対象） |

### `ITANDI` (`SHEET_NAMES.ITANDI`)

出力テンプレートではなく、入力データソース（紛らわしいがITANDIマイソクとは別物）。
建物名・部屋番号で`新規募集家賃管理`と突き合わせて使う。

| 列 | 項目 |
|---|---|
| A (index 0) | 建物名（突合キー） |
| C (index 2) | 部屋番号（突合キー） |
| E (index 4) | 専有面積 |
| H (index 7) | 所在地 |
| X (index 23) | 間取り |
| AA (index 26) | バイク置場 |
| AB (index 27) | 駐輪場 |
| AM (index 38) | 備考 |

### `入退去管理` (`SHEET_NAMES.MOVE_IN_OUT`)

最新の「解約申請」行から入居可能日を算出する。

| 列 | 項目 |
|---|---|
| B (index 1) | 申請日（新しい順ソートのキー） |
| C (index 2) | 種別（`"解約申請"`で絞り込み） |
| D (index 3) | 建物名（突合キー） |
| E (index 4) | 部屋番号（突合キー） |
| L (index 11) | 退去予定日 |

### `駐車場価格設定` (`SHEET_NAMES.PARKING`)

建物別の駐車場料金マスタ。

| 列 | 項目 |
|---|---|
| I (index 8) | 建物名（突合キー） |
| K (index 10) | 駐車場料金 |

## 新規追加タブ

### `ジョブ管理` (`SHEET_NAMES.JOB_QUEUE`)

1行 = 1(部屋×テンプレート)。列順は `gas/src/Config.ts` の `JOB_COLUMNS` と
`python/autohp/sheets_client.py` の `JOB_COLUMNS` を必ず一致させること
（列インデックスに依存した読み書きをしているため）。

`building_id`/`room_id`という独立したID列は使わない。実データ
（`新規募集家賃管理`）に該当する列が存在せず、建物名・部屋番号がそのまま
キーとして使われているため。

| 列 | 項目 | 説明 |
|---|---|---|
| A | batch_id | `JOB-YYYYMMDD-NNNN` |
| B | row_id | `{batch_id}-{template_type}-{建物名}-{部屋番号}` |
| C | building_name | |
| D | room_name | |
| E | template_type | `in_house` \| `general` \| `in_house_guarantee`（`itandi`は将来追加予定・現状未使用） |
| F | status | `WAITING` \| `PROCESSING` \| `COMPLETED` \| `ERROR` |
| G | created_at | ISO8601、GASがジョブ行追記時に設定 |
| H | claimed_at | PCがクレーム時に設定 |
| I | completed_at | 終了時（COMPLETED/ERROR）に設定 |
| J | error_message | サニタイズ済みの定型文のみ。内部パス・認証情報を含めない |
| K | output_a3_ref | 完了後のNAS出力先の相対パス（列名は歴史的経緯でA3のままだが、現状はA3のみ生成するため実質「NAS出力パス」列） |
| L | output_a4_ref | 一般・自社保証会社マイソクのみ、Drive完成品フォルダへアップロードした際のDriveファイルID（自社用は空欄。列名は歴史的経緯） |
| M | attempt_count | TransientErrorによる再試行回数 |
| N | worker_id | クレームしたPCプロセスの識別子（hostname:pid） |
| O | background_ref | Slidesエクスポート背景画像（文字情報焼き込み済み）のDriveファイルID |

### `レイアウト情報` (`SHEET_NAMES.LAYOUT_CAPTURE`)

`gas/src/LayoutCaptureTool.ts` の出力先。Slidesページ上のプレースホルダー要素を
数値化し、`templates/*.yaml` の座標を決める材料にする（写真配置座標が
未確定のため、これから実際に使う想定）。

| 列 | 項目 | 説明 |
|---|---|---|
| A | template_type | |
| B | slide_page_id | |
| C | element_name | プレースホルダーのtitle/objectId |
| D | element_type | `IMAGE` \| `TEXT` \| `SHAPE` |
| E | x_emu | `PageElement.transform.translateX` |
| F | y_emu | `PageElement.transform.translateY` |
| G | width_emu | `Size.width × scaleX` |
| H | height_emu | `Size.height × scaleY` |
| I | rotation_deg | transformから算出した回転角 |
| J | page_width_emu | ページ全体の幅（参照用） |
| K | page_height_emu | ページ全体の高さ（参照用） |
| L | captured_at | 取得日時 |

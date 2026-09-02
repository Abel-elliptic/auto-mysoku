# テンプレート設定ファイル仕様 (`templates/*.yaml`)

スキーマの実体は `python/autohp/template_config.py` のpydanticモデル。
このドキュメントはその要約。

## トップレベル項目

| キー | 型 | 説明 |
|---|---|---|
| `template_type` | str | `in_house` \| `general`（ファイル名と一致させる。`itandi`は将来追加予定・現状未使用） |
| `display_name` | str | 表示名（例: 自社マイソク） |
| `slides_template_file_id` | str | 背景生成に使うGoogle SlidesファイルID。`in_house`=`1QB2132Hz0XMREBKmxddQTp-9S34dijgy2oUeBODyVtM`、`general`=`1rr3v0UMjSqMDJPjAvBveoqnj7r210nllVgyTxO22jOc`（実データ確認済み） |
| `page_size.width_mm` / `height_mm` | float | A3基準の用紙サイズ（mm） |
| `dpi` | int | 既定300。`canvas_size_px()` でA3基準キャンバスpxを算出 |
| `required_images` | list[str] | 欠損時にジョブ全体をERRORにする画像スロットkey |
| `optional_images` | list[str] | 欠損しても処理を継続する画像スロットkey |
| `image_slots` | list[ImageSlot] | 画像の配置定義 |
| `text_fields` | list[TextField] | 文字の配置定義 |

## ImageSlot

| キー | 型 | 説明 |
|---|---|---|
| `key` | str | required_images/optional_imagesと対応させるスロット識別子 |
| `source` | `nas` \| `slides_export` | `nas`はNASから、`slides_export`はSlides背景から |
| `source_filename` | str \| null | `source: nas` の場合の固定ファイル名（例: `living.jpg`） |
| `x_px` / `y_px` / `width_px` / `height_px` | int | A3基準キャンバス上の配置矩形 |
| `fit` | `cover` \| `contain` \| `stretch` | 既定 `cover`。下記参照 |

### fit の挙動（重要）

画像は「指定座標に貼り付ける」のではなく「指定の四角の中に敷き詰める」という
考え方で扱う。

- **`cover`（既定）**: CSSの `object-fit: cover` と同じ。画像の縦横比を維持したまま、
  四角を隙間なく埋めるよう拡大縮小し、はみ出た部分は中央基準でトリミングする
  （見切れることを許容する）。
- `contain`: 縦横比を維持したまま四角の中に収まるよう縮小し、余白ができる。
  間取り図のように全体を見切れさせたくない画像に使う想定。
- `stretch`: 縦横比を無視して四角ぴったりに引き伸ばす。背景画像のフルブリード配置等に使う。

## TextField

**重要**: 実際に運用する `templates/in_house.yaml` / `templates/general.yaml` では
`text_fields` は空リストにしている。建物名・賃料・住所等の文字情報は、
既存のコード.js（実プロジェクトのファイル）の `updateSlideWithData()` が既にSlides側で
`replaceAllText()` により焼き込んでからエクスポートしているため、Pythonで
重ねて描画すると二重管理・表示崩れの原因になる。TextField描画機能自体は
`compositor.py` に残しているので、将来Slides側で扱いきれない文字要素が
出てきた場合はこのYAMLに追記して使うことができる。

| キー | 型 | 説明 |
|---|---|---|
| `key` | str | 識別子 |
| `room_data_field` | str | ジョブ行の対応するキー名（例: `rent`） |
| `x_px` / `y_px` | int | 描画開始座標 |
| `font_family` | str | 既定 `Noto Sans JP`（要確認: 実際のブランドフォント） |
| `font_size_px` | int | |
| `color` | str | `#RRGGBB` |
| `align` | `left` \| `center` \| `right` | 既定 `left` |
| `max_width_px` | int \| null | 指定時は折り返し/縮小対象（要確認: 詳細仕様） |

## A3→A4の扱い

テンプレートはA3基準の座標のみを持つ。A4はA3合成済み画像を
`compositor.downscale_a3_to_a4()` で1/√2倍に縮小するだけで生成するため、
A4専用の座標セットは定義しない（二重管理を避けるための設計判断）。

## 座標の決め方（次にやること・未実施）

現時点では `templates/in_house.yaml` / `templates/general.yaml` の
`image_slots` には背景（`background`、`source: slides_export`）しかなく、
写真の配置座標は未確定。以下の手順で実際のSlidesファイルから座標を取得する
必要がある（このリポジトリの作業としては未実施。実際のSlidesファイルへの
アクセス権を持つ人が行うこと）。

1. 実際のSlidesファイル（`in_house`は
   `1QB2132Hz0XMREBKmxddQTp-9S34dijgy2oUeBODyVtM`、`general`は
   `1rr3v0UMjSqMDJPjAvBveoqnj7r210nllVgyTxO22jOc`）を開き、写真を置きたい
   位置に仮の画像（またはプレースホルダー用の図形）を配置する。
2. スプレッドシートの「マイソク」メニュー →「レイアウト情報取得」を実行し、
   プロンプトにテンプレート種別（`in_house`/`general`）と対象SlidesファイルIDを
   入力する。「レイアウト情報」シートへ x/y/width/height(EMU)・回転角・
   ページサイズが出力される。
3. EMU値をpx（A3基準dpi換算、1pt=12700EMU、1インチ=72pt=914400EMU）へ変換し、
   対応する `templates/*.yaml` の `image_slots` へ写真スロットとして追記する
   （`source: nas`、`source_filename`にNAS上の写真ファイル名を指定）。
   変換の自動化ツールは未実装。
4. 座標を追記したら、`required_images` / `optional_images` にもそのスロットの
   `key` を追加すること（追加しないと`compositor.py`は写真を合成しない）。

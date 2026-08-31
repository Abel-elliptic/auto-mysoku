# auto-mysoku — マイソク自動生成システム

賃貸物件マイソク（募集図面）を、Google スプレッドシート起点で自動生成するシステム。
Canvaでの手作業を、GAS（司令塔）+ 社内PC上のPython（画像合成）+ NAS（画像保存）の
組み合わせに置き換える。

詳細設計は [`docs/architecture.md`](docs/architecture.md) を参照。

実際に本番運用中のスプレッドシート・GASコード（`gas/src/RentalDataLookup.ts`、
既存の`processNewRentals`等を移植・拡張したもの）と統合し、1回の「マイソク作成」
操作で自社マイソク・一般マイソクの2種類を生成する（ITANDIマイソクは将来追加予定）。

## 全体像

1. **Googleスプレッドシート**: 既存の「新規募集家賃管理」タブでJ列にチェックを入れて
   「マイソク作成」メニューを実行すると、GASが建物名・賃料・住所等の文字情報を
   Google Slidesへ焼き込んで画像化し、選択部屋 × 2テンプレート種別（自社/一般）分の
   ジョブが「ジョブ管理」タブにWAITING状態で登録される。
2. **社内PC（Python）**: 定期的にジョブ管理シートをポーリングし、WAITINGジョブを
   クレームして処理する。NAS上の部屋写真をSMB経由で取得し、テンプレート設定
   （`templates/*.yaml`）に従ってGAS側で作った文字入り背景の上へ写真を合成、
   NASへ保存し結果をシートへ報告する（写真配置座標は現時点で未確定 — 詳細は
   [`docs/architecture.md`](docs/architecture.md) の要確認事項12を参照）。
3. **NAS**: 元画像（`募集用/`）と生成済みマイソク（`マイソク/`, `自社マイソク/`）を
   保存する。外部ネットワークへは一切公開しない。

## セキュリティ方針

- NAS・社内PCをインターネットへ公開しない。ポート開放も行わない。
- 社内PCからGoogle API / NASへのアウトバウンド通信のみで完結させる。
- 認証情報はすべて環境変数/OS資格情報ストア経由（`.env.example` 参照、ハードコード禁止）。
- パストラバーサル対策・最小権限NASアカウント等、詳細は [`docs/security.md`](docs/security.md)。

## ディレクトリ構成

```
gas/        Google Apps Script（clasp管理）— スプレッドシート起点のジョブ生成・Slides背景生成
python/     社内PCで動くPythonプログラム（ジョブポーリング・画像合成・NAS I/O）
templates/  マイソクテンプレート種別ごとの設定（YAML）
docs/       設計ドキュメント
```

## セットアップ（開発時）

```bash
# Python側
cd python
pip install -e ".[dev]"
pytest

# GAS側
cd gas
npm install
npx tsc --noEmit      # 型チェック
cp .clasp.json.example .clasp.json  # scriptIdを実際の値に置き換えて使用
npx clasp push
```

`.env.example` を `.env` にコピーし、実際の値を設定してから
`python -m autohp.job_poller` で社内PC側のポーラーを起動する。

セットアップ後の一通りの動作確認は [`docs/verification.md`](docs/verification.md) の
手順に従って実施する。プログラミングに詳しくない方向けの、画面操作まで丁寧に説明した版は
[`docs/verification_beginner.md`](docs/verification_beginner.md) を参照。

## 未確定事項

多くの仕様は「要確認」として `docs/architecture.md` にまとめている。
特にNAS実機情報・スプレッドシート全項目・Slides背景の生成方式は、
実装を本番投入する前に必ず確認すること。

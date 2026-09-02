/**
 * 既存Apps Scriptプロジェクトのファイル（コード.js等）で定義される関数の
 * アンビエント宣言。それらのファイルは本番運用中のコード・機密情報を含むため
 * このリポジトリには含めず、clasp push時にローカルへ手動配置する運用にしている
 * （.gitignore・docs/architecture.md「既存Apps Scriptプロジェクトとの共存について」参照）。
 * そのため型チェック時にこのリポジトリ内から実体が見えず、素朴には型エラーになる。
 * この宣言はその実体を型チェッカーに教えるためだけのもので、実行時の型情報を
 * 持たない（.d.tsは常にコンパイル対象外）。
 */

declare function processNewRentals(is_own?: boolean, batchId?: string): void;

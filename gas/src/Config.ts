/**
 * シート名・テンプレート種別・Script Propertiesキー等、複数モジュールで
 * 共有する定数を集約する。DriveフォルダID・Slidesテンプレートファイル ID
 * 等の「環境ごとに変わる値」はソースへ直書きせず、Script Properties
 * (PropertiesService.getScriptProperties()) から取得する。
 */

// 実スプレッドシートの既存タブをそのまま利用する（新規タブは作らない）。
// 「新規募集家賃管理」のJ列チェックボックスが選択トリガー。
// 選択判定・文字埋め込みロジックは実プロジェクトの既存ファイル コード.js の
// processNewRentals()/updateSlideWithData() が担当する。このファイルは本番運用中の
// 他機能（DB同期・PDF出力等）や機密情報を含むためこのリポジトリには含めず、
// clasp push時にローカルのgas/src/へ手動配置する運用（docs/architecture.md参照）。
const SHEET_NAMES = {
  RENTAL_MANAGEMENT: "新規募集家賃管理",
  ITANDI: "ITANDI",
  MOVE_IN_OUT: "入退去管理",
  PARKING: "駐車場価格設定",
  JOB_QUEUE: "ジョブ管理", // 新規追加タブ
  LAYOUT_CAPTURE: "レイアウト情報", // 新規追加タブ（LayoutCaptureTool用）
} as const;

// ジョブ管理シートの列順。python/autohp/sheets_client.py の JOB_COLUMNS と
// 必ず一致させること（列インデックスに依存した読み書きをしているため）。
// building_id/room_idではなくbuilding_name/room_nameを使うのは、実データ
// （新規募集家賃管理シート）に独立したID列が存在せず、建物名・部屋番号が
// そのままキーとして使われているため。
const JOB_COLUMNS = [
  "batch_id",
  "row_id",
  "building_name",
  "room_name",
  "template_type",
  "status",
  "created_at",
  "claimed_at",
  "completed_at",
  "error_message",
  "output_a3_ref",
  "output_a4_ref",
  "attempt_count",
  "worker_id",
  "background_ref",
] as const;

// 実際に運用中のSlidesテンプレートは「自社(in_house)」「一般(general)」の2種類のみ。
// 「自社保証会社(in_house_guarantee)」は一般と同じSlidesファイルを使い、文言（保証会社・
// 火災保険・備考の一部）だけが異なる（コード.js側の分岐で処理する）。
// ITANDIマイソク相当のテンプレートはまだ存在しないため、型としては残しつつ
// バッチ生成対象（TEMPLATE_TYPES）からは外す（将来Slidesファイルが用意され次第追加する）。
type TemplateType = "in_house" | "itandi" | "general" | "in_house_guarantee";

const TEMPLATE_TYPES: TemplateType[] = ["in_house", "general", "in_house_guarantee"];

const SCRIPT_PROPERTY_KEYS = {
  BACKGROUND_DRIVE_FOLDER_ID: "BACKGROUND_DRIVE_FOLDER_ID",
  SLIDES_TEMPLATE_FILE_ID_PREFIX: "SLIDES_TEMPLATE_FILE_ID_", // + template_type
} as const;

function getScriptProperty(key: string): string {
  const value = PropertiesService.getScriptProperties().getProperty(key);
  if (!value) {
    throw new Error(`Script Property が未設定です: ${key}`);
  }
  return value;
}

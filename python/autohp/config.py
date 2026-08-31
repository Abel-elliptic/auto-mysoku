"""環境変数からの設定読み込み。

認証情報・パス等はソースコードへハードコードせず、すべて環境変数
（本番運用ではOS資格情報ストア/シークレットマネージャ経由での注入を推奨）
から取得する。`.env.example` に必要な変数一覧を記載している。
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Google API ---
    google_service_account_json_path: str = Field(
        ...,
        description="サービスアカウント鍵ファイルへの絶対パス。リポジトリ管理外の場所に置くこと。",
    )
    spreadsheet_id: str = Field(..., description="ジョブ管理スプレッドシートのID")

    # --- NAS / SMB ---
    smb_host: str = Field(..., description="NASのホスト名またはIPアドレス")
    smb_share: str = Field(..., description="接続先の共有名（例: share）")
    smb_username: str = Field(..., description="NAS専用・最小権限アカウントのユーザー名")
    smb_password: str = Field(..., description="上記アカウントのパスワード。可能ならOS資格情報ストア経由で注入する")
    nas_source_root: str = Field(
        default="募集用", description="部屋写真の格納ルート（共有内相対パス）"
    )
    # 生成済みマイソクの出力先は、共有直下に「マイソク」「自社マイソク」「ITANDIマイソク」の
    # 3つが兄弟フォルダとして並ぶ構成（仕様書のNASディレクトリ構造参照）。
    # 全テンプレート種別で共通の親フォルダは存在しないため、単一のnas_output_rootは持たない
    # （job_processor.OUTPUT_SUBTREEがテンプレート種別ごとの実際の共有直下フォルダ名を持つ）。

    # --- ジョブ処理 ---
    poll_interval_seconds: int = Field(
        default=30, description="要確認: 実運用でのポーリング間隔。ここではデフォルト値を仮置き"
    )
    max_retry_attempts: int = Field(
        default=3, description="要確認: TransientError時の最大リトライ回数。ここではデフォルト値を仮置き"
    )
    stale_processing_minutes: int = Field(
        default=10,
        description="要確認: PROCESSINGのまま放置されたと判定するまでの分数。ここではデフォルト値を仮置き",
    )
    worker_id: str | None = Field(
        default=None, description="未指定時は hostname:pid から自動生成する"
    )

    # --- ログ ---
    log_dir: str = Field(default="./logs", description="ログ出力ディレクトリ")
    log_retention_days: int = Field(default=30, description="要確認: ログ保持日数。デフォルト値を仮置き")


def load_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # 値は環境変数/.envから供給される

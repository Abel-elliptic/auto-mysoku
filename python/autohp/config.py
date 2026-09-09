"""環境変数からの設定読み込み。

認証情報・パス等はソースコードへハードコードせず、すべて環境変数
（本番運用ではOS資格情報ストア/シークレットマネージャ経由での注入を推奨）
から取得する。`.env.example` に必要な変数一覧を記載している。
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# .envはリポジトリ直下（このファイルから見て python/autohp/../.. ）に置く運用
# （docs/verification_beginner.md 参照）。pydantic-settingsのenv_fileは
# デフォルトでは「実行時のカレントディレクトリ」基準の相対パスになり、
# `cd python && python -m autohp.job_poller` のように python/ 配下で実行すると
# リポジトリ直下の.envを見つけられず、必須項目が未設定のまま起動時エラーになる。
# それを避けるため、このファイルの場所を基準にした絶対パスを使う。
_REPO_ROOT_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_REPO_ROOT_ENV_FILE, env_file_encoding="utf-8", extra="ignore"
    )

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
        default="営業画像", description="部屋写真の格納ルート（共有内相対パス）"
    )
    # 生成済みマイソク（完成品）の出力先は {nas_output_root}/{建物名}/{部屋番号}/マイソク/
    # の下に、テンプレート種別を問わず同じ「マイソク」フォルダへ、ファイル名の接頭辞
    # （マイソク_/自社保証会社_マイソク_/自社用マイソク_）で区別して並べる。
    # nas_output_root自体は共有内の相対パス（共有直下でよければ空文字のままでよい）。
    nas_output_root: str = Field(
        default="", description="完成品マイソクの出力先ルート（共有内相対パス、共有直下なら空文字）"
    )

    # --- Drive（完成品の一部を保存する先） ---
    # 一般(general)・自社保証会社(in_house_guarantee)の完成品のみ、ここにも保存する
    # （自社用(in_house)はNASのみ）。Drive APIは使わず、社内PCにGoogle Drive for
    # Desktop等で同期されているローカルフォルダへ直接ファイルを書き込む方式にしている
    # （サービスアカウントへのフォルダ共有・OAuth設定が不要でシンプルなため）。
    finished_drive_dir: str = Field(
        ..., description="完成品マイソク（一般・自社保証会社のみ）の保存先ローカルパス（Drive同期フォルダ）"
    )

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

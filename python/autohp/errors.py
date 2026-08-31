"""ジョブ処理で発生しうる例外の型。

TransientError と PermanentError を明確に分けることで、
job_poller / job_processor が「リトライすべきか」「即座に諦めるべきか」を
例外の型だけで判断できるようにする。
"""

from __future__ import annotations


class AutoHPError(Exception):
    """基底クラス。直接送出しない。"""

    def __init__(self, user_message: str, detail: str | None = None) -> None:
        # user_message: スプレッドシートのerror_messageへそのまま書き戻してよい定型文（日本語）。
        #   内部パス・認証情報・スタックトレースを絶対に含めないこと。
        # detail: ログにのみ出力する内部向け詳細情報。
        super().__init__(user_message)
        self.user_message = user_message
        self.detail = detail or user_message


class TransientError(AutoHPError):
    """NAS一時切断・API一時エラー等、再試行すれば成功しうる失敗。

    job_poller はこの例外を捕捉した行を WAITING に戻し attempt_count を増やす。
    """


class PermanentError(AutoHPError):
    """必須画像欠損・不正なファイル名・設定不備等、再試行しても変わらない失敗。

    job_poller はこの例外を捕捉した行を即座に ERROR にする（リトライしない）。
    """


class PathSafetyError(PermanentError):
    """建物名・部屋番号のサニタイズ、またはNASルート配下チェックに失敗した場合。"""


class MissingRequiredImageError(PermanentError):
    """テンプレートが必須と定義した画像スロットがNAS上に存在しない場合。"""

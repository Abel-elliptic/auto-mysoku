"""構造化ログ設定。

方針:
- 内部パス・スタックトレース・認証情報等の詳細は、このローカルログにのみ出力する。
- スプレッドシートへ書き戻す error_message は autohp.errors.AutoHPError.user_message
  （定型文）のみを使い、ここで扱う詳細情報とは完全に分離する。
- ローテーションは日次、保持日数は Settings.log_retention_days（要確認: 実運用値）。
"""

from __future__ import annotations

import json
import logging
import os
from logging.handlers import TimedRotatingFileHandler

from autohp.config import Settings


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("job_row_id", "worker_id", "stage"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(settings: Settings) -> None:
    os.makedirs(settings.log_dir, exist_ok=True)
    log_path = os.path.join(settings.log_dir, "autohp.log")

    file_handler = TimedRotatingFileHandler(
        log_path, when="midnight", backupCount=settings.log_retention_days, encoding="utf-8"
    )
    file_handler.setFormatter(JsonFormatter())

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    console_handler.setLevel(logging.INFO)

    root = logging.getLogger("autohp")
    root.setLevel(logging.DEBUG)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

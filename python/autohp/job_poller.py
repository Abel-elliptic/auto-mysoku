"""社内PC側のメインループ。

WAITING（および放置されたPROCESSING = 要確認 stale_processing_minutes超過分）
のジョブをポーリングし、楽観的クレームに成功したものだけ処理する。
TransientError は WAITING へ差し戻し（上限超過でERROR昇格）、
PermanentError は即ERRORにする。

社内PCからGoogle API / NASへのアウトバウンド接続のみを行い、
このプロセス自身は一切の待受ポートを開かない。
"""

from __future__ import annotations

import logging
import os
import socket
import time
from datetime import UTC, datetime, timedelta

from autohp.config import Settings, load_settings
from autohp.drive_client import DriveClient
from autohp.errors import PermanentError, TransientError
from autohp.job_processor import process
from autohp.logging_setup import setup_logging
from autohp.sheets_client import SheetsClient
from autohp.smb_client import SmbClient

logger = logging.getLogger("autohp.job_poller")


def _default_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def run_forever(settings: Settings | None = None) -> None:
    settings = settings or load_settings()
    setup_logging(settings)
    worker_id = settings.worker_id or _default_worker_id()
    logger.info("poller_start", extra={"worker_id": worker_id, "stage": "start"})

    sheets = SheetsClient(settings)
    drive = DriveClient(settings)

    templates_dir = os.environ.get("AUTOHP_TEMPLATES_DIR", "../templates")

    while True:
        try:
            _run_once(settings, sheets, drive, worker_id, templates_dir)
        except TransientError:
            logger.exception("poll_cycle_transient_error", extra={"worker_id": worker_id})
        except Exception:
            # ジョブ単位の例外は _run_once 内で個別に捕捉済み（1件のジョブの異常で
            # ループを止めない）。ここはさらにその外側、claim_job等ジョブ処理に
            # 入る前の想定外の例外に対する最後の砦。ここで捕まえずに落とすと、
            # 常駐プロセスであるポーラーが二度と自動復帰しなくなってしまう。
            logger.exception("poll_cycle_unexpected_error", extra={"worker_id": worker_id})
        time.sleep(settings.poll_interval_seconds)


def _run_once(
    settings: Settings, sheets: SheetsClient, drive: DriveClient, worker_id: str, templates_dir: str
) -> None:
    stale_before = (
        datetime.now(UTC) - timedelta(minutes=settings.stale_processing_minutes)
    ).isoformat()
    jobs = sheets.fetch_waiting_or_stale_jobs(stale_before)

    for job in jobs:
        if not sheets.claim_job(job, worker_id, stale_before):
            continue  # 他ワーカーが先にクレームした（またはまだ放棄判定に達していない）

        with SmbClient(settings) as smb:
            try:
                # ジョブ行の値（building_name/room_name等）をそのままroom_dataとして
                # 渡す。実運用テンプレート（in_house/general）はtext_fieldsを
                # 持たない（文字はGAS側でSlidesに焼き込み済みのため）ので、
                # room_dataはNASパス組み立てに使うbuilding_name/room_nameがあれば足りる。
                room_data = dict(job.values)
                process(job, room_data, templates_dir, settings, sheets, drive, smb)
            except PermanentError as exc:
                logger.exception(
                    "job_permanent_error",
                    extra={"job_row_id": job.row_id, "stage": "error", "worker_id": worker_id},
                )
                sheets.report_error(job, exc.user_message)
            except TransientError as exc:
                attempt = int(job.values.get("attempt_count", "0") or "0") + 1
                logger.exception(
                    "job_transient_error",
                    extra={"job_row_id": job.row_id, "stage": "retry", "worker_id": worker_id},
                )
                if attempt >= settings.max_retry_attempts:
                    sheets.report_error(
                        job, "一時的な処理エラーが複数回発生しました。管理者に確認してください。"
                    )
                else:
                    sheets.requeue_after_transient_failure(job, attempt, exc.user_message)
            except Exception:
                # 未分類の例外（設定不備・想定外のバグ等）。ここで捕まえずに伝播させると
                # run_forever() のループ自体が停止し、以後すべてのジョブが処理されなく
                # なってしまう。1件のジョブの異常でポーラー全体を巻き込まないよう、
                # このジョブだけをERRORにしてループは継続する。
                logger.exception(
                    "job_unexpected_error",
                    extra={"job_row_id": job.row_id, "stage": "error", "worker_id": worker_id},
                )
                sheets.report_error(
                    job, "想定外のエラーが発生しました。管理者に確認してください。"
                )


def main() -> None:
    run_forever()


if __name__ == "__main__":
    main()

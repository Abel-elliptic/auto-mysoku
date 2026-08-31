from unittest.mock import MagicMock, patch

from autohp.job_poller import _run_once
from autohp.sheets_client import JobRow


def _make_job(row_number: int = 2) -> JobRow:
    return JobRow(
        row_number=row_number,
        values={
            "batch_id": "JOB-1",
            "row_id": "JOB-1-0001",
            "template_type": "in_house",
            "status": "WAITING",
            "attempt_count": "0",
        },
    )


def test_unexpected_exception_in_process_does_not_propagate() -> None:
    """job_processor.process()がバグ等で未分類の例外を投げても、_run_once自体は
    例外を伝播させず、そのジョブをERROR報告して処理を継続すること
    （1件のジョブの異常でポーラー全体が停止してしまう回帰を防ぐ）。
    """
    job = _make_job()
    settings = MagicMock()
    settings.stale_processing_minutes = 10
    settings.max_retry_attempts = 3
    sheets = MagicMock()
    sheets.fetch_waiting_or_stale_jobs.return_value = [job]
    sheets.claim_job.return_value = True
    drive = MagicMock()

    with patch("autohp.job_poller.SmbClient") as smb_cls, patch(
        "autohp.job_poller.process", side_effect=ZeroDivisionError("boom")
    ):
        smb_cls.return_value.__enter__.return_value = MagicMock()

        # 例外が_run_once自体から外へ漏れ出さないことを確認する。
        _run_once(settings, sheets, drive, "worker-1", "../templates")

    assert sheets.report_error.called
    args = sheets.report_error.call_args.args
    assert args[0] is job
    # 内部の例外種別・詳細（"boom"等）をユーザー向けメッセージに含めないこと。
    assert "boom" not in args[1]
    assert "ZeroDivisionError" not in args[1]


def test_permanent_error_still_reports_sanitized_message() -> None:
    job = _make_job()
    settings = MagicMock()
    settings.stale_processing_minutes = 10
    settings.max_retry_attempts = 3
    sheets = MagicMock()
    sheets.fetch_waiting_or_stale_jobs.return_value = [job]
    sheets.claim_job.return_value = True
    drive = MagicMock()

    from autohp.errors import PermanentError

    with patch("autohp.job_poller.SmbClient") as smb_cls, patch(
        "autohp.job_poller.process",
        side_effect=PermanentError("必要な画像が見つかりません。", detail="/internal/path leaked"),
    ):
        smb_cls.return_value.__enter__.return_value = MagicMock()
        _run_once(settings, sheets, drive, "worker-1", "../templates")

    args = sheets.report_error.call_args.args
    assert args[1] == "必要な画像が見つかりません。"
    assert "/internal/path" not in args[1]

"""ジョブ管理シートの読み書きを行うクライアント。

社内PC -> Google API へのアウトバウンドHTTPS通信のみで完結する
（Google側からPCへ接続を開くことは一切ない）。

クレーム(WAITING->PROCESSING)は「該当行を再読込→書込→再読込で確認」という
楽観的ロックで行う。Sheets APIには compare-and-swap 相当のプリミティブが
無いため完全な排他ではないが、ポーラーが少数（基本1台）である前提では
実用上十分。要確認: 複数PCで同時稼働させる運用があるか。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from autohp.config import Settings
from autohp.errors import TransientError

logger = logging.getLogger("autohp.sheets")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

JOB_SHEET_NAME = "ジョブ管理"
# 建物名(A列)→マンション/戸建て(C列)の対応表。コード.js getBuildingType()と
# 同じシートを参照する（外観写真の格納場所が建物単位か部屋単位かの判定に使う）。
BUILDING_LIST_SHEET_NAME = "建物一覧"

# ジョブ管理シートの列順（A列から）。GAS側 Config.ts と一致させること。
# building_id/room_idではなくbuilding_name/room_nameを使うのは、実データ
# （新規募集家賃管理シート）に独立したID列が存在せず、建物名・部屋番号が
# そのままキーとして使われているため（gas/src/RentalDataLookup.ts参照）。
JOB_COLUMNS = [
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
]

STATUS_COL = JOB_COLUMNS.index("status")

# JOB_COLUMNS の列数から末尾の列文字を導出する（列追加時にA2:N等の
# ハードコードされた終端とズレて末尾列が読み落とされることを防ぐ）。
_LAST_COL_LETTER = chr(ord("A") + len(JOB_COLUMNS) - 1)


def is_claimable(status: str, claimed_at: str, stale_before_iso: str) -> bool:
    """指定した状態のジョブ行がクレーム可能（WAITING、または放棄されたPROCESSING）かを判定する。

    Sheets APIへのI/Oを含まない純粋関数として切り出し、ユニットテスト可能にしている。
    """
    if status == "WAITING":
        return True
    return status == "PROCESSING" and claimed_at < stale_before_iso


@dataclass
class JobRow:
    row_number: int  # シート上の行番号(1始まり、ヘッダー行込み)
    values: dict[str, str]

    @property
    def row_id(self) -> str:
        return self.values.get("row_id", "")

    @property
    def template_type(self) -> str:
        return self.values.get("template_type", "")


class SheetsClient:
    def __init__(self, settings: Settings) -> None:
        creds = service_account.Credentials.from_service_account_file(
            settings.google_service_account_json_path, scopes=SCOPES
        )
        self._service = build("sheets", "v4", credentials=creds)
        self._spreadsheet_id = settings.spreadsheet_id

    def _values(self) -> object:
        return self._service.spreadsheets().values()

    def fetch_building_type(self, building_name: str) -> str:
        """「建物一覧」シートのA列(建物名)を検索し、C列(マンション/戸建て)を返す。

        見つからない場合は空文字を返す（戸建判定は文字列に"戸建"が含まれるかで
        行うため、空文字は「戸建てではない＝マンション扱い」の安全側に倒れる）。
        """
        try:
            resp = (
                self._values()
                .get(spreadsheetId=self._spreadsheet_id, range=f"{BUILDING_LIST_SHEET_NAME}!A2:C")
                .execute()
            )
        except HttpError as exc:
            raise TransientError("建物一覧の取得に失敗しました。", detail=str(exc)) from exc

        for row in resp.get("values", []):
            if row and row[0] == building_name:
                return row[2] if len(row) > 2 else ""
        return ""

    def fetch_waiting_or_stale_jobs(self, stale_before_iso: str) -> list[JobRow]:
        try:
            resp = (
                self._values()
                .get(spreadsheetId=self._spreadsheet_id, range=f"{JOB_SHEET_NAME}!A2:{_LAST_COL_LETTER}")
                .execute()
            )
        except HttpError as exc:
            raise TransientError("ジョブ一覧の取得に失敗しました。", detail=str(exc)) from exc

        rows: list[JobRow] = []
        for idx, raw in enumerate(resp.get("values", []), start=2):
            padded = raw + [""] * (len(JOB_COLUMNS) - len(raw))
            values = dict(zip(JOB_COLUMNS, padded))
            if is_claimable(values.get("status", ""), values.get("claimed_at", ""), stale_before_iso):
                rows.append(JobRow(row_number=idx, values=values))
        return rows

    def claim_job(self, job: JobRow, worker_id: str, stale_before_iso: str) -> bool:
        """該当行のみ再読込→WAITING（または放棄されたPROCESSING）であれば書込→
        再読込で確認する楽観的クレーム。

        放棄判定は「claimed_atがstale_before_isoより古いPROCESSING行」で行う。
        以前の実装は「現在のworker_idと一致するPROCESSING行のみ再クレーム可」という
        条件になっており、これだとクラッシュした別ワーカーが掴んだままの行を
        新しいワーカーが決して再取得できない（新ワーカーのworker_idは常に異なるため）
        というバグがあったため、claimed_at基準の判定に修正した。
        """
        current = self._read_single_row(job.row_number)
        if not is_claimable(current.get("status", ""), current.get("claimed_at", ""), stale_before_iso):
            return False

        now = _now_iso()
        self._write_row_fields(
            job.row_number, {"status": "PROCESSING", "claimed_at": now, "worker_id": worker_id}
        )
        confirm = self._read_single_row(job.row_number)
        return confirm.get("worker_id") == worker_id and confirm.get("status") == "PROCESSING"

    def report_completed(self, job: JobRow, output_a3_ref: str, output_a4_ref: str) -> None:
        self._write_row_fields(
            job.row_number,
            {
                "status": "COMPLETED",
                "completed_at": _now_iso(),
                "output_a3_ref": output_a3_ref,
                "output_a4_ref": output_a4_ref,
                "error_message": "",
            },
        )

    def report_error(self, job: JobRow, sanitized_message: str) -> None:
        self._write_row_fields(
            job.row_number,
            {"status": "ERROR", "completed_at": _now_iso(), "error_message": sanitized_message},
        )

    def requeue_after_transient_failure(self, job: JobRow, attempt_count: int, message: str) -> None:
        self._write_row_fields(
            job.row_number,
            {
                "status": "WAITING",
                "attempt_count": str(attempt_count),
                "error_message": message,
            },
        )

    def _read_single_row(self, row_number: int) -> dict[str, str]:
        try:
            resp = (
                self._values()
                .get(
                    spreadsheetId=self._spreadsheet_id,
                    range=f"{JOB_SHEET_NAME}!A{row_number}:{_LAST_COL_LETTER}{row_number}",
                )
                .execute()
            )
        except HttpError as exc:
            raise TransientError("ジョブ行の再読込に失敗しました。", detail=str(exc)) from exc
        raw = (resp.get("values") or [[]])[0]
        padded = raw + [""] * (len(JOB_COLUMNS) - len(raw))
        return dict(zip(JOB_COLUMNS, padded))

    def _write_row_fields(self, row_number: int, fields: dict[str, str]) -> None:
        data = []
        for key, value in fields.items():
            col_idx = JOB_COLUMNS.index(key)
            col_letter = chr(ord("A") + col_idx)
            data.append(
                {"range": f"{JOB_SHEET_NAME}!{col_letter}{row_number}", "values": [[value]]}
            )
        try:
            self._values().batchUpdate(
                spreadsheetId=self._spreadsheet_id,
                body={"valueInputOption": "RAW", "data": data},
            ).execute()
        except HttpError as exc:
            raise TransientError("ジョブ行の更新に失敗しました。", detail=str(exc)) from exc


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()

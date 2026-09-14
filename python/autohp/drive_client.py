"""Google Slidesがエクスポートした背景画像等、大きめのバイナリをDriveから取得する。

ジョブ本体の状態管理はSheetsが正だが、背景PNGのような大きいファイルは
Sheetsセルに収まらないためDriveフォルダ経由で受け渡す（GAS側で
Driveへアップロードし、そのfile_idをジョブ行に書き込む設計。詳細は
gas/src/SlidesBackgroundGenerator.ts を参照）。

ジョブがCOMPLETEDになった後は、この背景PNG（あくまで合成前の一時ファイル）は
不要になるため job_processor.py が削除する。削除にはBACKGROUND_DRIVE_FOLDER_ID
フォルダへのサービスアカウントの共有権限を「閲覧者」から「編集者」へ上げておく
必要がある（閲覧者権限では削除できない）。
"""

from __future__ import annotations

import io
import logging

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from autohp.config import Settings
from autohp.errors import TransientError

logger = logging.getLogger("autohp.drive")

# 背景PNGの削除（COMPLETED後のクリーンアップ）も行うため、読み取り専用スコープでは足りない。
SCOPES = ["https://www.googleapis.com/auth/drive"]


class DriveClient:
    def __init__(self, settings: Settings) -> None:
        creds = service_account.Credentials.from_service_account_file(
            settings.google_service_account_json_path, scopes=SCOPES
        )
        self._service = build("drive", "v3", credentials=creds)

    def download_file(self, file_id: str) -> bytes:
        try:
            request = self._service.files().get_media(fileId=file_id)
            buf = io.BytesIO()
            downloader = MediaIoBaseDownload(buf, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            return buf.getvalue()
        except HttpError as exc:
            raise TransientError(
                "背景画像の取得に失敗しました。", detail=f"Drive download failed for {file_id}: {exc}"
            ) from exc

    def delete_file(self, file_id: str) -> None:
        """一時保存の背景PNGを削除する。COMPLETED後のクリーンアップ専用。"""
        try:
            self._service.files().delete(fileId=file_id).execute()
        except HttpError as exc:
            raise TransientError(
                "背景画像の削除に失敗しました。", detail=f"Drive delete failed for {file_id}: {exc}"
            ) from exc

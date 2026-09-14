"""Google Slidesがエクスポートした背景画像等、大きめのバイナリをDriveから取得する。

ジョブ本体の状態管理はSheetsが正だが、背景PNGのような大きいファイルは
Sheetsセルに収まらないためDriveフォルダ経由で受け渡す（GAS側で
Driveへアップロードし、そのfile_idをジョブ行に書き込む設計。詳細は
gas/src/SlidesBackgroundGenerator.ts を参照）。

ジョブがCOMPLETEDになった後は、この背景PNG（あくまで合成前の一時ファイル）は
不要になるため job_processor.py が削除する。削除にはBACKGROUND_DRIVE_FOLDER_ID
フォルダへのサービスアカウントの共有権限を「閲覧者」から「編集者」へ上げておく
必要がある（閲覧者権限では削除できない）。

削除は完全削除(files.delete)ではなくゴミ箱へ移動(trashed=true)で行う。
このファイルの所有者はGASを実行した人間のGoogleアカウント（folder.createFile()）で
あり、サービスアカウントは編集者にすぎない。Google Driveでは非所有者の編集者は
files.delete()（完全削除）を実行できず403 insufficientFilePermissionsになるため、
編集者でも実行できるtrashed=trueへの更新を使う。
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
        """一時保存の背景PNGをゴミ箱へ移動する。COMPLETED後のクリーンアップ専用。

        既に存在しないファイル（例: 同じジョブ行を手動でWAITINGへ戻して再テスト
        した等で、前回の処理で既に削除済みのケース）はDriveが404を返すが、
        「削除したい対象が既に存在しない」＝目的は達成済みなのでエラー扱いにしない。
        """
        try:
            self._service.files().update(fileId=file_id, body={"trashed": True}).execute()
        except HttpError as exc:
            if exc.resp is not None and exc.resp.status == 404:
                logger.info(
                    "background_already_deleted", extra={"stage": "cleanup", "file_id": file_id}
                )
                return
            raise TransientError(
                "背景画像の削除に失敗しました。", detail=f"Drive delete failed for {file_id}: {exc}"
            ) from exc

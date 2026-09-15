"""NAS(SMB)への読み書きを行うクライアント。

path_safety.SafePath 型のみを受け取り、生の文字列パスからのファイル
アクセスは一切行わない（うっかりバイパスを型レベルで防ぐ）。

要確認: 実際のNAS製品（Synology/QNAP/Windows Server等）・共有名・
認証方式（ユーザー名/パスワード固定か、都度取得のトークンか）。
ここでは smbprotocol (SMB2/3対応) を用いる想定で実装するが、
smbclient 高水準APIが使えない特殊な認証要件があれば要調整。
"""

from __future__ import annotations

import logging
import uuid
from typing import Self

import spnego
from smbprotocol.connection import Connection
from smbprotocol.exceptions import SMBException
from smbprotocol.session import Session
from smbprotocol.tree import TreeConnect

from autohp.config import Settings
from autohp.errors import TransientError
from autohp.path_safety import SafePath

logger = logging.getLogger("autohp.smb")

# Windowsのタスクスケジューラで非対話ログオン（SYSTEMアカウントやS4U）から
# ポーラーを起動すると、smbprotocolが認証に使うpyspnegoが既定で選ぶ
# Windowsネイティブ実装(SSPI)経由のNTLM認証が
# 「パッケージに提供された資格情報は認識されませんでした」で失敗する
# （SSPIの明示的な資格情報によるNTLM認証は対話ログオンセッションでしか
# 動かないというWindows側の制約。手動でターミナルを開いて実行した場合は
# 対話セッションなので発生しない）。
# NegotiateOptions.use_ntlm を強制し、SSPIを迂回してpyspnego純正Python実装の
# NTLMを使わせることで、非対話セッションでも認証できるようにする。
_original_spnego_client = spnego.client


def _spnego_client_force_ntlm(*args: object, **kwargs: object) -> spnego.ContextProxy:
    kwargs["options"] = kwargs.get("options", spnego.NegotiateOptions.none) | spnego.NegotiateOptions.use_ntlm
    return _original_spnego_client(*args, **kwargs)


spnego.client = _spnego_client_force_ntlm


class SmbClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._connection: Connection | None = None
        self._session: Session | None = None
        self._tree: TreeConnect | None = None

    def connect(self) -> None:
        s = self._settings
        try:
            self._connection = Connection(uuid.uuid4(), s.smb_host, port=445)
            self._connection.connect()
            self._session = Session(self._connection, s.smb_username, s.smb_password)
            self._session.connect()
            self._tree = TreeConnect(self._session, f"\\\\{s.smb_host}\\{s.smb_share}")
            self._tree.connect()
            logger.info("smb_connected", extra={"host": s.smb_host, "share": s.smb_share})
        except SMBException as exc:
            raise TransientError(
                "NASへの接続に失敗しました。",
                detail=f"SMB connect failed: {exc}",
            ) from exc

    def close(self) -> None:
        for closable in (self._tree, self._session, self._connection):
            try:
                if closable is not None:
                    closable.disconnect()
            except SMBException:
                logger.warning("smb_close_failed", exc_info=True)

    def __enter__(self) -> Self:
        self.connect()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def read_file(self, path: SafePath) -> bytes:
        """SafePath の指すファイルを読み込む。存在しない場合は None 相当として
        呼び出し側 (job_processor) が FileNotFoundError を判定できるよう送出する。
        """
        from smbclient import open_file  # smbprotocol付属の高水準API

        try:
            with open_file(
                self._windows_path(path),
                mode="rb",
                username=self._settings.smb_username,
                password=self._settings.smb_password,
            ) as f:
                return f.read()
        except FileNotFoundError:
            raise
        except SMBException as exc:
            raise TransientError(
                "NAS上のファイル読み込みに失敗しました。",
                detail=f"SMB read failed for {path.as_posix()}: {exc}",
            ) from exc

    def write_file(self, path: SafePath, data: bytes) -> None:
        from smbclient import makedirs, open_file

        try:
            parent = "\\".join(path.relative_parts[:-1])
            if parent:
                makedirs(
                    f"\\\\{self._settings.smb_host}\\{self._settings.smb_share}\\{parent}",
                    exist_ok=True,
                    username=self._settings.smb_username,
                    password=self._settings.smb_password,
                )
            with open_file(
                self._windows_path(path),
                mode="wb",
                username=self._settings.smb_username,
                password=self._settings.smb_password,
            ) as f:
                f.write(data)
        except SMBException as exc:
            raise TransientError(
                "NASへのファイル書き込みに失敗しました。",
                detail=f"SMB write failed for {path.as_posix()}: {exc}",
            ) from exc

    def _windows_path(self, path: SafePath) -> str:
        relative = "\\".join(path.relative_parts)
        return f"\\\\{self._settings.smb_host}\\{self._settings.smb_share}\\{relative}"

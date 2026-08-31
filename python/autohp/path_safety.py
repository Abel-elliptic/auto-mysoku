"""NAS上のパスをスプレッドシート由来の文字列（建物名・部屋番号等）から
安全に組み立てるための唯一の窓口。

設計方針:
- 個々のパスセグメントはホワイトリスト正規表現で検証し、一致しなければ
  ファイルシステム操作を一切行わずに PathSafetyError を送出する。
- セグメントを結合したパスは常にこのモジュールの safe_join() 経由でのみ
  生成させる。他モジュール（smb_client 等）は生の文字列パスを受け取らず、
  本モジュールが返す SafePath 型のみを受け取ることで、うっかりバイパスする
  ことをコンパイル/型チェックの時点で防ぐ。
- 許可ルート配下に収まっているかは、結合後のパスを正規化してから
  「区切り文字を含めた前方一致」で判定する（"/root_evil" が "/root" に
  誤って一致しないようにするため）。

要確認: 実際の建物名・部屋番号のサンプルが未提供のため、許容文字種
（全角括弧・スペース・ハイフン等）は仮の設定になっている。実データを
確認した上で厳格化/緩和すること。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from autohp.errors import PathSafetyError

# 要確認: 実際の建物名・部屋番号に使われる文字種のサンプルが必要。
# ここでは「英数字・漢字/かな/カナ・一部の全角記号・ハイフン/アンダースコア/スペース」
# を仮に許可し、パス区切り文字・相対参照・NUL文字等は一切許可しない。
_SAFE_SEGMENT_RE = re.compile(
    r"^[A-Za-z0-9一-龥ぁ-んァ-ヶー"
    r"（）\(\)\[\]・\-_\. 　]+$"
)

_FORBIDDEN_SEGMENTS = {".", ".."}


@dataclass(frozen=True)
class SafePath:
    """許可ルート配下であることが検証済みのパス。

    smb_client はこの型のみを受け取り、生の str を受け取らない。
    """

    relative_parts: tuple[str, ...]

    def as_posix(self) -> str:
        return "/".join(self.relative_parts)


def sanitize_segment(name: str) -> str:
    """建物名・部屋番号・ファイル名など、パスの1階層分を検証する。"""
    if not name or name in _FORBIDDEN_SEGMENTS:
        raise PathSafetyError(
            "入力値に不正な文字が含まれています。",
            detail=f"invalid path segment (empty or dot): {name!r}",
        )
    if not _SAFE_SEGMENT_RE.match(name):
        raise PathSafetyError(
            "入力値に不正な文字が含まれています。",
            detail=f"path segment failed allowlist: {name!r}",
        )
    return name


def safe_join(root: str, *segments: str) -> SafePath:
    """root（NAS共有内の許可ルート、例: "募集用"）配下に限定して
    segments を結合した SafePath を返す。

    root 自体は設定値（環境変数）由来で信頼できる想定のためサニタイズ対象外だが、
    segments はすべてユーザー入力（スプレッドシート由来）とみなし検証する。
    """
    sanitized = [sanitize_segment(root)] if root else []
    for seg in segments:
        sanitized.append(sanitize_segment(seg))

    # PurePosixPath で正規化（SMB共有内の仮想パス空間なので、ローカルOSの
    # realpath ではなく論理的な正規化のみを行う）。
    candidate = PurePosixPath(*sanitized)
    normalized_parts = tuple(p for p in candidate.parts if p not in ("/", ""))

    allowed_root_parts = (sanitize_segment(root),) if root else ()
    if normalized_parts[: len(allowed_root_parts)] != allowed_root_parts:
        raise PathSafetyError(
            "許可されていないパスへのアクセスが要求されました。",
            detail=f"resolved path {normalized_parts} escapes allowed root {allowed_root_parts}",
        )
    if any(part in _FORBIDDEN_SEGMENTS for part in normalized_parts):
        raise PathSafetyError(
            "入力値に不正な文字が含まれています。",
            detail=f"normalized path still contains dot-segments: {normalized_parts}",
        )

    return SafePath(relative_parts=normalized_parts)

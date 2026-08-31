"""ジョブ1件 (部屋 x テンプレート) を処理する。

処理ステップ:
1. テンプレート設定をロード
2. ジョブ行の値（building_name/room_name等）をroom_dataとして使う
   （実運用テンプレートはtext_fieldsを持たないため、文字情報の取得は
   本質的には不要。NASパス組み立てにbuilding_name/room_nameのみ使う）
3. 背景画像をDriveから取得（GAS側で文字を焼き込み済みのSlidesエクスポート画像）
4. NASから必要画像を取得。取得できたものだけ RoomImages に積む
5. 必須画像の欠損チェック → 欠損があればジョブ全体をPermanentErrorにする
6. 合成 → A3画像、そこからA4画像を生成
7. NASの出力先へ書き込み（`{date}_A3.jpg` / `{date}_A4.jpg`）
8. 完了報告
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from autohp.compositor import RoomImages, check_required_images, composite_flyer, downscale_a3_to_a4
from autohp.config import Settings
from autohp.drive_client import DriveClient
from autohp.errors import MissingRequiredImageError, PermanentError
from autohp.path_safety import safe_join
from autohp.sheets_client import JobRow, SheetsClient
from autohp.smb_client import SmbClient
from autohp.template_config import TemplateConfig, load_template_config_by_type

logger = logging.getLogger("autohp.job_processor")

# テンプレート種別ごとの、NAS共有直下の出力フォルダ名（仕様書のNASディレクトリ構造どおり、
# マイソク/自社マイソク/ITANDIマイソクは共有直下に並ぶ兄弟フォルダであり、共通の親フォルダの
# 下にネストしない。したがってこの値自体がsafe_join()に渡す許可ルートになる）。
OUTPUT_SUBTREE = {
    "in_house": "自社マイソク",
    "itandi": "ITANDIマイソク",
    "general": "マイソク",
}


def process(
    job: JobRow,
    room_data: dict[str, str],
    templates_dir: str,
    settings: Settings,
    sheets: SheetsClient,
    drive: DriveClient,
    smb: SmbClient,
) -> None:
    logger.info("job_start", extra={"job_row_id": job.row_id, "stage": "start"})

    template = load_template_config_by_type(templates_dir, job.template_type)

    building_name = room_data.get("building_name", "")
    room_name = room_data.get("room_name", "")

    background_bytes = _fetch_background(job, drive)

    images = RoomImages(
        by_key=_fetch_room_images(template, building_name, room_name, smb, settings.nas_source_root)
    )

    missing = check_required_images(template, set(images.by_key.keys()))
    if missing:
        raise MissingRequiredImageError(
            f"必要な画像が見つかりません（{'、'.join(missing)}）。",
            detail=f"missing required images for {building_name}/{room_name}: {missing}",
        )

    from io import BytesIO

    from PIL import Image

    background_img = Image.open(BytesIO(background_bytes)).convert("RGB") if background_bytes else Image.new(
        "RGB", template.canvas_size_px(), "white"
    )

    a3_image = composite_flyer(template, room_data, background_img, images)
    a4_image = downscale_a3_to_a4(a3_image)

    today = datetime.now(UTC).date().isoformat().replace("-", "")
    output_root = OUTPUT_SUBTREE.get(job.template_type, job.template_type)
    a3_path = safe_join(output_root, building_name, room_name, f"{today}_A3.jpg")
    a4_path = safe_join(output_root, building_name, room_name, f"{today}_A4.jpg")

    smb.write_file(a3_path, _jpeg_bytes(a3_image))
    smb.write_file(a4_path, _jpeg_bytes(a4_image))

    sheets.report_completed(job, a3_path.as_posix(), a4_path.as_posix())
    logger.info("job_completed", extra={"job_row_id": job.row_id, "stage": "completed"})


def _fetch_background(job: JobRow, drive: DriveClient) -> bytes | None:
    background_ref = job.values.get("background_ref")  # 要確認: 実カラム名/存在有無
    if not background_ref:
        return None
    return drive.download_file(background_ref)


def _fetch_room_images(
    template: TemplateConfig,
    building_name: str,
    room_name: str,
    smb: SmbClient,
    source_root: str,
) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for slot in template.image_slots:
        if slot.source != "nas" or not slot.source_filename:
            continue
        try:
            path = safe_join(source_root, building_name, room_name, slot.source_filename)
        except PermanentError:
            # サニタイズ失敗＝不正な建物名/部屋番号。そのスロットは欠損扱いとし、
            # 必須スロットであれば check_required_images() 側でERRORになる。
            logger.warning(
                "image_path_rejected", extra={"job_row_id": "", "stage": "fetch_images"}
            )
            continue
        try:
            result[slot.key] = smb.read_file(path)
        except FileNotFoundError:
            continue
    return result


def _jpeg_bytes(image: object) -> bytes:
    from io import BytesIO

    buf = BytesIO()
    image.save(buf, format="JPEG", quality=92)  # type: ignore[attr-defined]
    return buf.getvalue()

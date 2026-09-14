"""ジョブ1件 (部屋 x テンプレート) を処理する。

処理ステップ:
1. テンプレート設定をロード
2. ジョブ行の値（building_name/room_name等）をroom_dataとして使う
   （実運用テンプレートはtext_fieldsを持たないため、文字情報の取得は
   本質的には不要。ファイル名・NASパス組み立てにbuilding_name/room_nameを使う）
3. 背景画像をDriveから取得（GAS側で文字を焼き込み済みのSlidesエクスポート画像）
4. NASから必要画像を取得。取得できたものだけ RoomImages に積む
5. 必須画像の欠損チェック → 欠損があればジョブ全体をPermanentErrorにする
6. 合成 → A3サイズの完成品画像を生成（A4は作らない）
7. NASの出力先へ書き込み: {nas_output_root}/{building_name}/{room_name}/マイソク/
   {yyyymmdd}_{ファイル名}.jpg
8. 一般(general)・自社保証会社(in_house_guarantee)の完成品のみ、さらに
   settings.finished_drive_dir（社内PCでGoogle Drive for Desktop等により
   同期されているローカルフォルダ）へも {ファイル名}.jpg（日付なし）で保存する
   （自社用(in_house)はNASのみ。Drive APIは使わずローカルファイル書き込みで済ませる）
9. 完了報告
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from autohp.compositor import RoomImages, check_required_images, composite_flyer
from autohp.config import Settings
from autohp.drive_client import DriveClient
from autohp.errors import MissingRequiredImageError, PermanentError
from autohp.path_safety import safe_join, sanitize_segment
from autohp.sheets_client import JobRow, SheetsClient
from autohp.smb_client import SmbClient
from autohp.template_config import TemplateConfig, load_template_config_by_type

logger = logging.getLogger("autohp.job_processor")

# テンプレート種別ごとの完成品ファイル名の接頭辞。
FILENAME_PREFIX = {
    "in_house": "自社用マイソク_",
    "general": "マイソク_",
    "in_house_guarantee": "自社保証会社_マイソク_",
}

# このテンプレート種別の完成品のみ、NASに加えてDriveへもアップロードする。
DRIVE_UPLOAD_TEMPLATE_TYPES = {"general", "in_house_guarantee"}

# NAS出力先で、建物名/部屋番号の下に置く固定のサブフォルダ名
# （テンプレート種別を問わず同じフォルダに、ファイル名の接頭辞で区別して並べる）。
NAS_OUTPUT_SUBFOLDER = "マイソク"

# 部屋の写真（間取り・外観・キッチン等）は部屋によって拡張子がjpg/pngなど
# バラバラなため、ImageSlot.source_filenameに拡張子を含めない場合はこの順で
# 試す（見つかった最初のものを使う）。既に拡張子を含む値（"." を含む）を
# 指定した場合はそのまま1回だけ試し、このリストは使わない。
CANDIDATE_IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp"]


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
    # 戸建は建物=部屋が実質1つしかないため、外観写真も部屋番号フォルダの中に
    # 入る（マンションのように建物直下に外観だけ置く運用ではない）。
    is_detached_house = "戸建" in sheets.fetch_building_type(building_name)

    background_bytes = _fetch_background(job, drive)

    images = RoomImages(
        by_key=_fetch_room_images(
            template, building_name, room_name, smb, settings.nas_source_root, is_detached_house
        )
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

    flyer_image = composite_flyer(template, room_data, background_img, images)
    flyer_bytes = _jpeg_bytes(flyer_image)

    prefix = FILENAME_PREFIX.get(job.template_type)
    if prefix is None:
        raise PermanentError(
            "未対応のテンプレート種別です。",
            detail=f"no FILENAME_PREFIX for template_type={job.template_type!r}",
        )
    # building_name/room_nameはスプレッドシート由来のためファイル名へ使う前に検証する
    # （safe_join()と同じホワイトリストチェック。パス区切り文字等は通らない）。
    safe_building_name = sanitize_segment(building_name)
    safe_room_name = sanitize_segment(room_name)
    filename = f"{prefix}{safe_building_name}{safe_room_name}.jpg"

    today = datetime.now(UTC).date().isoformat().replace("-", "")
    nas_path = safe_join(
        settings.nas_output_root, building_name, room_name, NAS_OUTPUT_SUBFOLDER, f"{today}_{filename}"
    )
    smb.write_file(nas_path, flyer_bytes)

    drive_ref = ""
    if job.template_type in DRIVE_UPLOAD_TEMPLATE_TYPES:
        drive_path = Path(settings.finished_drive_dir) / filename
        drive_path.write_bytes(flyer_bytes)
        drive_ref = str(drive_path)

    # JOB_COLUMNSのoutput_a3_ref/output_a4_ref列を、NAS出力パス/Drive完成品の保存先
    # パスの記録用に転用している（A3/A4の2サイズ出力をやめたため列名の意味は変わったが、
    # 列自体の追加・GAS側との同期を避けるため既存の2列をそのまま使う）。
    sheets.report_completed(job, nas_path.as_posix(), drive_ref)
    logger.info("job_completed", extra={"job_row_id": job.row_id, "stage": "completed"})

    _cleanup_background(job, drive)


def _cleanup_background(job: JobRow, drive: DriveClient) -> None:
    """COMPLETED後、合成に使い終えた一時保存の背景PNGをDriveから削除する。

    完成品は既にNAS/Driveへ書き込み済み・シートへも報告済みのため、この
    削除に失敗してもジョブ自体は失敗させない（次回の手動整理に任せる）。
    """
    background_ref = job.values.get("background_ref")
    if not background_ref:
        return
    try:
        drive.delete_file(background_ref)
    except Exception:
        logger.warning(
            "background_cleanup_failed", extra={"job_row_id": job.row_id, "stage": "cleanup"}
        )


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
    is_detached_house: bool,
) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for slot in template.image_slots:
        if slot.source != "nas" or not slot.source_filename:
            continue
        candidates = (
            [slot.source_filename]
            if "." in slot.source_filename
            else [f"{slot.source_filename}{ext}" for ext in CANDIDATE_IMAGE_EXTENSIONS]
        )
        # 戸建は建物直下に外観だけ置く運用がそもそも成立しない（棟=部屋のため）ので、
        # source_scope="building" のスロットでも部屋番号フォルダの中を見る。
        use_building_scope = slot.source_scope == "building" and not is_detached_house
        path_segments = (building_name,) if use_building_scope else (building_name, room_name)
        for filename in candidates:
            try:
                path = safe_join(source_root, *path_segments, filename)
            except PermanentError:
                # サニタイズ失敗＝不正な建物名/部屋番号。そのスロットは欠損扱いとし、
                # 必須スロットであれば check_required_images() 側でERRORになる。
                logger.warning(
                    "image_path_rejected", extra={"job_row_id": "", "stage": "fetch_images"}
                )
                break
            try:
                result[slot.key] = smb.read_file(path)
                break
            except FileNotFoundError:
                continue
    return result


def _jpeg_bytes(image: object) -> bytes:
    from io import BytesIO

    buf = BytesIO()
    image.save(buf, format="JPEG", quality=92)  # type: ignore[attr-defined]
    return buf.getvalue()

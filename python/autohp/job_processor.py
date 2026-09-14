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
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

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

# NASファイル名の日付は日本の営業日基準（JST）で付与する。社内PCはOS設定に
# 関わらずこの固定タイムゾーンで計算するため、サーバーのタイムゾーン設定に
# 依存しない（datetime.now(UTC)のままだとJST 0時〜9時台にUTCの前日日付が
# 付いてしまうバグがあったため修正）。
JST = ZoneInfo("Asia/Tokyo")

# NAS出力先で、建物名/部屋番号の下に置く固定のサブフォルダ名
# （テンプレート種別を問わず同じフォルダに、ファイル名の接頭辞で区別して並べる）。
NAS_OUTPUT_SUBFOLDER = "マイソク"

# 完成品JPEGの目標上限サイズ（バイト）。NAS/Driveの容量節約のため、画質・
# 解像度を段階的に落としてこのサイズ以下に収める。
MAX_OUTPUT_BYTES = 300_000

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

    today = datetime.now(JST).date().isoformat().replace("-", "")
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

    # 一時保存の背景PNGの削除はGAS側（gas/src/BackgroundCleanup.ts、
    # 時間主導型トリガーで定期実行）が担当する。この背景PNGはGAS実行時の
    # Googleアカウントが所有者であり、サービスアカウント（Python側）は
    # 非所有者の編集者止まりのため、Drive側の共有ポリシー次第では削除
    # （ゴミ箱への移動を含む）が拒否されることが実際にあった。所有者自身の
    # GASに削除させることで、この権限問題を構造的に回避する。


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


def _jpeg_bytes(image: object, max_bytes: int = MAX_OUTPUT_BYTES) -> bytes:
    """MAX_OUTPUT_BYTES以下になるまで、まず画質→それでも収まらなければ
    解像度を段階的に落としてJPEGへエンコードする。

    印刷用途のためいきなり低画質にはせず、まず画質(quality)側で絞り、
    画質を最低ラインまで落としても収まらない場合のみ解像度を縮小する
    （縦横比は維持）。
    """
    from io import BytesIO

    def encode(img: object, quality: int) -> bytes:
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=quality)  # type: ignore[attr-defined]
        return buf.getvalue()

    quality = 90
    data = encode(image, quality)
    while len(data) > max_bytes and quality > 40:
        quality -= 10
        data = encode(image, quality)

    current_image = image
    scale = 0.9
    while len(data) > max_bytes and scale > 0.3:
        width, height = current_image.size  # type: ignore[attr-defined]
        resized = current_image.resize(  # type: ignore[attr-defined]
            (max(1, int(width * scale)), max(1, int(height * scale)))
        )
        data = encode(resized, quality)
        current_image = resized
        scale -= 0.1

    return data

"""Pillowによる画像合成処理。

方針:
- 画像スロットは「指定座標に貼り付ける」のではなく「指定の四角
  (x_px, y_px, width_px, height_px) の中に敷き詰める」という考え方で扱う。
  デフォルトの fit="cover" は CSS の object-fit: cover と同じ挙動：
  画像の縦横比を維持したまま、四角を隙間なく埋めるよう拡大縮小し、
  はみ出た部分は中央基準でトリミングする（見切れることを許容する）。
- A4はA3合成後の縮小生成のみで作る（テンプレート側にA4用の座標は持たせない）。
  ISO 216のA系列は相似（縦横比が全サイズで共通）なので、A3画像を
  1/√2倍に縮小するだけでA4の正しいアスペクト比・内容になる。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from autohp.errors import PermanentError
from autohp.template_config import TemplateConfig, TextField

A3_TO_A4_SCALE = 1 / math.sqrt(2)


@dataclass
class RoomImages:
    """スロットkey -> 画像バイト列。取得できなかったスロットはキーごと存在しない。"""

    by_key: dict[str, bytes]


def _fit_image(img: Image.Image, width_px: int, height_px: int, fit: str) -> Image.Image:
    if fit == "stretch":
        return img.resize((width_px, height_px), Image.LANCZOS)

    src_w, src_h = img.size
    target_ratio = width_px / height_px
    src_ratio = src_w / src_h

    if fit == "cover":
        if src_ratio > target_ratio:
            # 元画像の方が横長 → 高さを基準に拡大し、左右をトリミング
            scale = height_px / src_h
        else:
            scale = width_px / src_w
        new_w, new_h = round(src_w * scale), round(src_h * scale)
        resized = img.resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - width_px) // 2
        top = (new_h - height_px) // 2
        return resized.crop((left, top, left + width_px, top + height_px))

    if fit == "contain":
        if src_ratio > target_ratio:
            scale = width_px / src_w
        else:
            scale = height_px / src_h
        new_w, new_h = round(src_w * scale), round(src_h * scale)
        resized = img.resize((new_w, new_h), Image.LANCZOS)
        canvas = Image.new("RGBA", (width_px, height_px), (255, 255, 255, 0))
        canvas.paste(resized, ((width_px - new_w) // 2, (height_px - new_h) // 2))
        return canvas

    raise PermanentError(f"未知のfitモードが指定されました: {fit}", detail=f"fit={fit}")


def _load_font(field: TextField) -> ImageFont.FreeTypeFont:
    # 要確認: 実際のフォントファイル配置場所。見つからない場合はPillow同梱の
    # デフォルトフォントにフォールバックする（表示品質は本番未確定）。
    try:
        return ImageFont.truetype(field.font_family, field.font_size_px)
    except OSError:
        return ImageFont.load_default()


def composite_flyer(
    template: TemplateConfig,
    room_data: dict[str, str],
    background: Image.Image,
    images: RoomImages,
) -> Image.Image:
    canvas_w, canvas_h = template.canvas_size_px()
    canvas = Image.new("RGB", (canvas_w, canvas_h), "white")

    for slot in template.image_slots:
        img_bytes: bytes | None
        if slot.source == "slides_export":
            img_bytes = _image_to_bytes(background)
        else:
            img_bytes = images.by_key.get(slot.key)

        if img_bytes is None:
            # 必須スロットの欠損は job_processor.check_required_images() で
            # ジョブ全体をERRORにする前提のため、ここに到達するのは任意画像の欠損のみ。
            continue

        slot_img = Image.open(BytesIO(img_bytes)).convert("RGBA")
        fitted = _fit_image(slot_img, slot.width_px, slot.height_px, slot.fit)
        canvas.paste(fitted.convert("RGB"), (slot.x_px, slot.y_px), fitted if fitted.mode == "RGBA" else None)

    draw = ImageDraw.Draw(canvas)
    for field in template.text_fields:
        value = room_data.get(field.room_data_field, "")
        font = _load_font(field)
        draw.text((field.x_px, field.y_px), str(value), fill=field.color, font=font, anchor=None)

    return canvas


def _image_to_bytes(img: Image.Image) -> bytes:
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def downscale_a3_to_a4(a3_image: Image.Image) -> Image.Image:
    """A3合成済み画像をA4サイズへ縮小する。

    A3とA4はISO 216のA系列であり縦横比が共通（√2:1）なため、
    幅・高さともに 1/√2 倍するだけで正しいA4画像になる
    （再合成やA4専用座標は不要）。
    """
    w, h = a3_image.size
    new_size = (round(w * A3_TO_A4_SCALE), round(h * A3_TO_A4_SCALE))
    return a3_image.resize(new_size, Image.LANCZOS)


def check_required_images(template: TemplateConfig, available_keys: set[str]) -> list[str]:
    """必須画像スロットのうち available_keys に無いものの一覧を返す（空なら欠損なし）。"""
    return [key for key in template.required_images if key not in available_keys]

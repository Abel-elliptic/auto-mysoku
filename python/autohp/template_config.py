"""マイソクテンプレート設定（templates/*.yaml）のスキーマとローダー。

テンプレートごとに「どの画像をどの四角に配置するか」「どの文字情報を
どこに書くか」を宣言的に定義する。コード変更なしにレイアウト調整できる
ようにするための唯一の設定源。
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, PositiveFloat, PositiveInt

FitMode = Literal["cover", "contain", "stretch"]
ImageSource = Literal["nas", "slides_export"]
# "room": {source_root}/{building}/{room}/{filename}（部屋ごとの写真、既定）
# "building": {source_root}/{building}/{filename}（外観等、建物単位で1枚しかない写真）
ImageSourceScope = Literal["room", "building"]


class PageSize(BaseModel):
    width_mm: PositiveFloat
    height_mm: PositiveFloat


class ImageSlot(BaseModel):
    key: str
    source: ImageSource = "nas"
    # source="nas" の場合、NAS上の {building}/{room}/{source_filename}
    # （source_scope="building"なら {building}/{source_filename}）を読む。
    source_filename: str | None = None
    # 外観のように部屋ごとではなく建物に1枚しかない写真は "building" を指定する。
    source_scope: ImageSourceScope = "room"
    x_px: int
    y_px: int
    # width_px/height_pxが0や負の値だと compositor._fit_image() がゼロ除算で
    # クラッシュする（cover/containの拡大縮小率計算 width_px/src_w 等）ため、
    # 設定ロード時点で弾く（実行時に画像を取得してから初めて気づく事態を防ぐ）。
    width_px: PositiveInt
    height_px: PositiveInt
    # fit のデフォルトは "cover"：CSSのobject-fit:coverと同じ考え方で、
    # 画像の縦横比を維持したまま指定の四角(width_px×height_px)を隙間なく
    # 埋めるように拡大し、はみ出た部分はトリミングする（見切れを許容する）。
    # 「座標に貼り付ける」のではなく「四角の中に敷き詰める」という発想。
    fit: FitMode = "cover"


class TextField(BaseModel):
    key: str
    room_data_field: str  # ジョブ行のキー名（例: building_name）に対応
    x_px: int
    y_px: int
    font_family: str = "Noto Sans JP"  # 要確認: 実際のブランドフォント
    font_size_px: PositiveInt = 32
    color: str = "#000000"
    align: Literal["left", "center", "right"] = "left"
    max_width_px: int | None = None  # 指定時は折り返し/自動縮小の対象（要確認: 挙動の詳細仕様）


class TemplateConfig(BaseModel):
    template_type: str
    display_name: str
    slides_template_file_id: str = Field(
        default="REPLACE_ME", description="要確認: 実際のGoogle SlidesテンプレファイルID"
    )
    page_size: PageSize
    dpi: PositiveInt = 300
    required_images: list[str] = Field(default_factory=list)
    optional_images: list[str] = Field(default_factory=list)
    image_slots: list[ImageSlot]
    text_fields: list[TextField]

    def canvas_size_px(self) -> tuple[int, int]:
        """A3基準キャンバスのピクセルサイズ（幅, 高さ）を dpi から算出する。

        1インチ=25.4mm。A3(420x297mm)@300dpiなら概ね4961x3508px。
        """
        width_px = round(self.page_size.width_mm / 25.4 * self.dpi)
        height_px = round(self.page_size.height_mm / 25.4 * self.dpi)
        return width_px, height_px


def load_template_config(path: str | Path) -> TemplateConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return TemplateConfig.model_validate(raw)


def load_template_config_by_type(templates_dir: str | Path, template_type: str) -> TemplateConfig:
    """template_type ("in_house" 等) から templates/{template_type}.yaml を解決してロードする。"""
    candidate = Path(templates_dir) / f"{template_type}.yaml"
    if not candidate.exists():
        raise FileNotFoundError(f"template config not found: {candidate}")
    return load_template_config(candidate)

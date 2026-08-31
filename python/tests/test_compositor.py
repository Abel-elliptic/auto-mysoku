import math

import pytest
from PIL import Image

from autohp.compositor import _fit_image, check_required_images, downscale_a3_to_a4
from autohp.template_config import ImageSlot, PageSize, TemplateConfig


def _make_template(**overrides: object) -> TemplateConfig:
    base: dict[str, object] = {
        "template_type": "in_house",
        "display_name": "社内マイソク",
        "page_size": PageSize(width_mm=420, height_mm=297),
        "dpi": 300,
        "required_images": ["living", "kitchen"],
        "optional_images": ["exterior"],
        "image_slots": [
            ImageSlot(key="living", source_filename="living.jpg", x_px=0, y_px=0, width_px=100, height_px=100)
        ],
        "text_fields": [],
    }
    base.update(overrides)
    return TemplateConfig(**base)  # type: ignore[arg-type]


def test_canvas_size_px_matches_a3_300dpi() -> None:
    template = _make_template()
    w, h = template.canvas_size_px()
    # A3 420x297mm @300dpi ≈ 4961 x 3508 px
    assert w == 4961
    assert h == 3508


def test_downscale_a3_to_a4_matches_iso216_ratio() -> None:
    a3 = Image.new("RGB", (4961, 3508))
    a4 = downscale_a3_to_a4(a3)
    # A4 297x210mm @300dpi ≈ 3508 x 2480 px（独立丸め込みの誤差で±1pxのずれは許容する）
    assert a4.size[0] == pytest.approx(3508, abs=1)
    assert a4.size[1] == pytest.approx(2480, abs=1)
    # アスペクト比がA3と一致すること（√2:1）
    assert math.isclose(a3.size[0] / a3.size[1], a4.size[0] / a4.size[1], rel_tol=1e-3)


def test_fit_cover_preserves_aspect_and_fills_target() -> None:
    src = Image.new("RGB", (200, 100))  # 横長
    result = _fit_image(src, width_px=50, height_px=50, fit="cover")
    assert result.size == (50, 50)


def test_fit_stretch_ignores_aspect_ratio() -> None:
    src = Image.new("RGB", (200, 100))
    result = _fit_image(src, width_px=50, height_px=50, fit="stretch")
    assert result.size == (50, 50)


def test_check_required_images_reports_missing() -> None:
    template = _make_template()
    missing = check_required_images(template, available_keys={"living"})
    assert missing == ["kitchen"]


def test_check_required_images_empty_when_all_present() -> None:
    template = _make_template()
    missing = check_required_images(template, available_keys={"living", "kitchen"})
    assert missing == []

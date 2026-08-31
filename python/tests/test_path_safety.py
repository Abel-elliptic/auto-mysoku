import pytest

from autohp.errors import PathSafetyError
from autohp.path_safety import safe_join, sanitize_segment


def test_sanitize_segment_allows_normal_name() -> None:
    assert sanitize_segment("建物A") == "建物A"
    assert sanitize_segment("101") == "101"
    assert sanitize_segment("メゾン・ド・テスト(101)") == "メゾン・ド・テスト(101)"


@pytest.mark.parametrize(
    "bad",
    [
        "..",
        ".",
        "",
        "../../etc/passwd",
        "foo/bar",
        "foo\\bar",
        "foo\x00bar",
        "C:\\Windows",
    ],
)
def test_sanitize_segment_rejects_traversal_and_separators(bad: str) -> None:
    with pytest.raises(PathSafetyError):
        sanitize_segment(bad)


def test_safe_join_stays_within_root() -> None:
    result = safe_join("募集用", "建物A", "101", "living.jpg")
    assert result.relative_parts == ("募集用", "建物A", "101", "living.jpg")
    assert result.as_posix() == "募集用/建物A/101/living.jpg"


def test_safe_join_rejects_dot_dot_segment() -> None:
    with pytest.raises(PathSafetyError):
        safe_join("募集用", "..", "secrets")


def test_safe_join_rejects_path_separator_inside_segment() -> None:
    with pytest.raises(PathSafetyError):
        safe_join("募集用", "建物A/../../etc", "101", "living.jpg")


def test_safe_join_does_not_confuse_sibling_prefix() -> None:
    # "募集用_evil" のような、rootを文字列としてだけ前方一致させると誤って
    # 通ってしまいそうなケースが正しく弾かれることを確認する。
    with pytest.raises(PathSafetyError):
        sanitize_segment("../募集用_evil")

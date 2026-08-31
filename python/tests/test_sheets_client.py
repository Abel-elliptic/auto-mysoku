from autohp.sheets_client import is_claimable


def test_waiting_row_is_always_claimable() -> None:
    assert is_claimable("WAITING", claimed_at="", stale_before_iso="2026-01-01T00:00:00+00:00")


def test_fresh_processing_row_is_not_claimable() -> None:
    # claimed_at が stale_before_iso より新しい（まだ放棄判定に達していない）
    assert not is_claimable(
        "PROCESSING",
        claimed_at="2026-01-01T00:05:00+00:00",
        stale_before_iso="2026-01-01T00:00:00+00:00",
    )


def test_stale_processing_row_is_claimable_regardless_of_original_worker() -> None:
    # クラッシュした別ワーカーが掴んだままの行でも、claimed_atが古ければ再クレーム可能に
    # なっているべき（worker_id一致を条件にしていた旧実装のバグの回帰テスト）。
    assert is_claimable(
        "PROCESSING",
        claimed_at="2025-12-31T23:00:00+00:00",
        stale_before_iso="2026-01-01T00:00:00+00:00",
    )


def test_completed_and_error_rows_are_never_claimable() -> None:
    assert not is_claimable("COMPLETED", claimed_at="", stale_before_iso="2026-01-01T00:00:00+00:00")
    assert not is_claimable("ERROR", claimed_at="", stale_before_iso="2026-01-01T00:00:00+00:00")

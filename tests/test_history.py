from datetime import datetime, timezone
from pathlib import Path

from ip_strategy.history import HISTORY_FILENAME, append_levels_history, history_filename
from ip_strategy.models import StrategyLevels


def test_history_filename_uses_expiry() -> None:
    assert history_filename("26-12-2026") == "history-26.12.26.csv"
    assert history_filename(None) == HISTORY_FILENAME
    assert history_filename("garbage") == HISTORY_FILENAME


def test_append_levels_history_writes_csv(tmp_path: Path) -> None:
    dt = datetime(2026, 8, 6, 6, 0, 0, tzinfo=timezone.utc)
    levels = StrategyLevels(
        success=True,
        computed_at=dt,
        ideal_premium=42.5,
        lhs=100.0,
        rhs=110.0,
    )
    path = append_levels_history(tmp_path, levels)
    assert path is not None
    text = (tmp_path / HISTORY_FILENAME).read_text(encoding="utf-8")
    assert "computed_at,computed_at_ist,ideal_premium,lhs,rhs" in text
    assert "42.5" in text
    assert "100.0" in text
    assert "110.0" in text
    assert "IST" in text

    append_levels_history(tmp_path, levels)
    assert (tmp_path / HISTORY_FILENAME).read_text(encoding="utf-8").count("\n") == 3


def test_append_levels_history_uses_per_expiry_filename(tmp_path: Path) -> None:
    dt = datetime(2026, 8, 6, 6, 0, 0, tzinfo=timezone.utc)
    levels = StrategyLevels(
        success=True,
        computed_at=dt,
        expiry_date="26-12-2026",
        ideal_premium=42.5,
        lhs=100.0,
        rhs=110.0,
    )
    path = append_levels_history(tmp_path, levels)
    assert path == tmp_path / "history-26.12.26.csv"
    assert path.is_file()


def test_append_levels_history_skips_failed_run(tmp_path: Path) -> None:
    dt = datetime(2026, 8, 6, 6, 0, 0, tzinfo=timezone.utc)
    levels = StrategyLevels(success=False, computed_at=dt, error="fail")
    assert append_levels_history(tmp_path, levels) is None
    assert not (tmp_path / HISTORY_FILENAME).exists()

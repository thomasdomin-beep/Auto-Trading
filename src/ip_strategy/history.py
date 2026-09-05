from __future__ import annotations

import csv
import logging
from pathlib import Path

from ip_strategy.models import StrategyLevels

logger = logging.getLogger(__name__)

HISTORY_FILENAME = "history.csv"
HISTORY_HEADER = (
    "computed_at",
    "computed_at_ist",
    "ideal_premium",
    "lhs",
    "rhs",
)


def history_filename(expiry_date: str | None) -> str:
    """history-dd.mm.yy.csv for a given DD-MM-YYYY expiry, else the default history.csv."""
    if not expiry_date:
        return HISTORY_FILENAME
    parts = expiry_date.split("-")
    if len(parts) != 3:
        return HISTORY_FILENAME
    dd, mm, yyyy = parts
    if not (dd.isdigit() and mm.isdigit() and yyyy.isdigit()):
        return HISTORY_FILENAME
    yy = yyyy[-2:]
    return f"history-{dd}.{mm}.{yy}.csv"


def append_levels_history(out_dir: Path, levels: StrategyLevels) -> Path | None:
    """Append one row per successful run for historical analysis.

    Rows are written to a per-expiry file named history-dd.mm.yy.csv (derived from
    levels.expiry_date), falling back to history.csv if no expiry is known.
    """
    if not levels.success:
        return None
    if (
        levels.lhs is None
        or levels.rhs is None
        or levels.ideal_premium is None
    ):
        return None

    path = out_dir / history_filename(levels.expiry_date)
    write_header = not path.is_file() or path.stat().st_size == 0
    ts = levels.computed_at.isoformat()
    row = (
        ts,
        levels.computed_at_ist,
        levels.ideal_premium,
        levels.lhs,
        levels.rhs,
    )
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(HISTORY_HEADER)
        writer.writerow(row)
    logger.info("Appended history row to %s", path)
    return path

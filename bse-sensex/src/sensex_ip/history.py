from __future__ import annotations

import csv
import logging
from pathlib import Path

from sensex_ip.models import StrategyLevels

logger = logging.getLogger(__name__)

HISTORY_FILENAME = "history.csv"
HISTORY_HEADER = (
    "computed_at",
    "computed_at_ist",
    "ideal_premium",
    "support",
    "resistance",
)


def append_levels_history(out_dir: Path, levels: StrategyLevels) -> Path | None:
    if not levels.success:
        return None
    if (
        levels.support is None
        or levels.resistance is None
        or levels.ideal_premium is None
    ):
        return None

    path = out_dir / HISTORY_FILENAME
    write_header = not path.is_file() or path.stat().st_size == 0
    row = (
        levels.computed_at.isoformat(),
        levels.computed_at_ist,
        levels.ideal_premium,
        levels.support,
        levels.resistance,
    )
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(HISTORY_HEADER)
        writer.writerow(row)
    logger.info("Appended history row to %s", path)
    return path

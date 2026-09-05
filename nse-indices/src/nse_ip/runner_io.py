from __future__ import annotations

import logging
from pathlib import Path

import pyperclip

from nse_ip.config import AppConfig
from nse_ip.models import StrategyLevels

logger = logging.getLogger(__name__)


def write_levels(cfg: AppConfig, levels: StrategyLevels) -> Path:
    out_dir = cfg.output_path
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "levels.json"

    if not levels.success and cfg.preserve_levels_on_failure and path.is_file():
        logger.warning("Run failed (%s); preserving previous levels.json", levels.error)
        (out_dir / "last_failure.json").write_text(
            levels.model_dump_json(indent=2), encoding="utf-8"
        )
        return path

    path.write_text(levels.model_dump_json(indent=2), encoding="utf-8")
    return path


def maybe_clipboard(cfg: AppConfig, levels: StrategyLevels) -> None:
    if not cfg.auto_clipboard or not levels.success:
        return
    if levels.support is None or levels.resistance is None:
        return
    try:
        pyperclip.copy(f"{levels.support}\n{levels.resistance}")
    except pyperclip.PyperclipException as e:
        logger.warning("Clipboard copy failed: %s", e)

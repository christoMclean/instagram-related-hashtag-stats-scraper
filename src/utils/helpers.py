from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List

# Configure a shared logger for the entire project
logger = logging.getLogger("instagram_hashtag_scraper")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

def load_settings(path: Path) -> Dict[str, Any]:
    """
    Load JSON settings from disk, with sensible defaults if the file
    cannot be read.
    """
    default_settings: Dict[str, Any] = {
        "instagram_base_url": "https://www.instagram.com",
        "request_timeout": 10,
        "max_retries": 3,
        "sleep_between_requests": 1.0,
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
        "output_dir": "../data",
    }

    if not path.exists():
        logger.warning(
            "Settings file %s not found. Using default settings.", path
        )
        return default_settings

    try:
        with path.open("r", encoding="utf-8") as f:
            loaded = json.load(f)
        if not isinstance(loaded, dict):
            logger.warning(
                "Settings file %s is not a JSON object. Using defaults.", path
            )
            return default_settings
        default_settings.update(loaded)
        return default_settings
    except Exception as exc:
        logger.error("Failed to load settings from %s: %s", path, exc)
        return default_settings

def resolve_output_dir(settings: Dict[str, Any], override: str | None) -> Path:
    """
    Decide where to write output files, using either an explicit override
    from CLI or the output_dir entry from settings.json.
    """
    if override:
        output_dir = Path(override).expanduser()
    else:
        output_dir_value = settings.get("output_dir", "../data")
        output_dir = Path(output_dir_value).expanduser()

    # Make path relative to this file's parent when not absolute
    if not output_dir.is_absolute():
        output_dir = Path(__file__).resolve().parents[2] / output_dir

    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Resolved output directory to %s", output_dir)
    return output_dir

def load_hashtag_list(path: Path | str) -> List[str]:
    """
    Read a newline-delimited list of hashtags from a text file.
    Blank lines and comment-style lines starting with '#' are ignored.
    """
    p = Path(path)
    items: List[str] = []
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            raw = line.strip()
            if not raw:
                continue
            if raw.startswith("//"):
                continue
            # Allow comment-style lines that start with '# ' but keep pure tags
            if raw.startswith("# ") or raw.startswith("//"):
                continue
            tag = raw.lstrip("#").strip()
            if tag:
                items.append(tag)
    # Deduplicate while preserving order
    seen = set()
    deduped: List[str] = []
    for tag in items:
        if tag not in seen:
            seen.add(tag)
            deduped.append(tag)
    return deduped

def humanize_posts_count(value: int) -> str:
    """
    Turn a large integer into a compact human-readable unit, such as:
      1234      -> "1.23 K"
      5600000   -> "5.6 M"
      2150000000 -> "2.15 G"
    """
    units = ["", "K", "M", "G", "T"]
    n = float(value)
    unit_idx = 0
    while abs(n) >= 1000 and unit_idx < len(units) - 1:
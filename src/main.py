import argparse
import json
import sys
from pathlib import Path
from typing import List, Dict, Any

# Ensure local imports work when running from project root
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from extractors.hashtag_parser import HashtagParser, HashtagStats
from extractors.post_collector import PostCollector
from extractors.relations_mapper import RelationsMapper
from exporters.data_exporter import DataExporter
from utils.helpers import (
    logger,
    load_settings,
    load_hashtag_list,
    resolve_output_dir,
)

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Instagram Related Hashtag Stats Scraper"
    )
    parser.add_argument(
        "-i",
        "--input-file",
        type=str,
        default=None,
        help="Path to a text file containing hashtags (one per line). "
             "If omitted, data/inputs.sample.txt will be used if present.",
    )
    parser.add_argument(
        "-t",
        "--tags",
        nargs="*",
        default=None,
        help="List of hashtags to process (e.g. love travel photography). "
             "Overrides --input-file if provided.",
    )
    parser.add_argument(
        "-f",
        "--formats",
        type=str,
        default="json,csv",
        help="Comma-separated list of output formats: json,csv,excel,html",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=str,
        default=None,
        help="Output directory for generated files. "
             "Defaults to the 'data' directory from settings.json.",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        default=str(CURRENT_DIR / "config" / "settings.json"),
        help="Path to settings.json configuration file.",
    )
    return parser

def discover_default_input_file() -> Path | None:
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from utils.helpers import logger

class DataExporter:
    """
    Handles exporting hashtag analytics to multiple formats:
    JSON, CSV, Excel, and HTML.
    """

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _prepare_flat_row(record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Flatten nested portions of the record to make CSV/Excel output
        easier to consume. Lists and dicts are JSON-encoded.
        """
        flat: Dict[str, Any] = {}

        for key, value in record.items():
            if isinstance(value, (list, dict)):
                flat[key] = json.dumps(value, ensure_ascii=False)
            else:
                flat[key] = value

        return flat

    def export_json(self, records: Iterable[Dict[str, Any]]) -> Path:
        records_list = list(records)
        output_path = self.output_dir / "hashtags.json"
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(records_list, f, ensure_ascii=False, indent=2)
        logger.info("Wrote JSON output to %s", output_path)
        return output_path

    def export_csv(self, records: Iterable[Dict[str, Any]]) -> Path:
        records_list = list(records)
        if not records_list:
            logger.warning("No records provided to export_csv.")
            return self.output_dir / "hashtags.csv"

        flat_records: List[Dict[str, Any]] = [
            self._prepare_flat_row(rec) for rec in records_list
        ]

        fieldnames = sorted({key for rec in flat_records for key in rec.keys()})

        output_path = self.output_dir / "hashtags.csv"
        with output_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for rec in flat_records:
                writer.writerow(rec)

        logger.info("Wrote CSV output to %s", output_path)
        return output_path

    def export_excel(self, records: Iterable[Dict[str, Any]]) -> Path:
        try:
            import pandas as pd
        except ImportError as exc:
            logger.error(
                "pandas is required for Excel export but is not installed: %s", exc
            )
            raise

        records_list = list(records)
        if not records_list:
            logger.warning("No records provided to export_excel.")
            return self.output_dir / "hashtags.xlsx"

        flat_records: List[Dict[str, Any]] = [
            self._prepare_flat_row(rec) for rec in records_list
        ]

        df = pd.DataFrame(flat_records)
        output_path = self.output_dir / "hashtags.xlsx"
        df.to_excel(output_path, index=False)
        logger.info("Wrote Excel output to %s", output_path)
        return output_path

    def export_html(self, records: Iterable[Dict[str, Any]]) -> Path:
        try:
            import pandas as pd
        except ImportError as exc:
            logger.error(
                "pandas is required for HTML export but is not installed: %s", exc
            )
            raise

        records_list = list(records)
        if not records_list:
            logger.warning("No records provided to export_html.")
            return self.output_dir / "hashtags.html"

        flat_records: List[Dict[str, Any]] = [
            self._prepare_flat_row(rec) for rec in records_list
        ]

        df = pd.DataFrame(flat_records)
        html_table = df.to_html(index=False, border=0, classes="hashtag-table")

        output_path = self.output_dir / "hashtags.html"
        with output_path.open("w", encoding="utf-8") as f:
            f.write(
                "<!DOCTYPE html>\n<html><head><meta charset='utf-8'>"
                "<title>Hashtag Analytics</title></head><body>\n"
            )
            f.write(html_table)
            f.write("\n</body></html>")

        logger.info("Wrote HTML output to %s", output_path)
        return output_path

    def export(self, records: Iterable[Dict[str, Any]], formats: List[str]) -> None:
        """
        Dispatch export to the requested formats.
        """
        formats_set = {fmt.lower() for fmt in formats}
        records_list = list(records)  # we iterate multiple times

        if "json" in formats_set:
            self.export_json(records_list)
        if "csv" in formats_set:
            self.export_csv(records_list)
        if "excel" in formats_set or "xlsx" in formats_set:
            self.export_excel(records_list)
        if "html" in formats_set:
            self.export_html(records_list)
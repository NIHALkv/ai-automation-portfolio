"""Append every run to an Excel log; fall back to CSV if the workbook is open/locked.

Uses openpyxl only (no pandas) so the Windows .exe stays small.
"""
from __future__ import annotations

import csv
from pathlib import Path

from openpyxl import Workbook, load_workbook

HEADERS = ["run_started", "report", "status", "file", "error"]


def append_log(cfg: dict, summary) -> Path:
    rows = [[summary.started, r.name, r.status, r.file, r.error] for r in summary.results]
    path = Path(cfg["download_root"]) / "Download_Log.xlsx"
    try:
        if path.exists():
            wb = load_workbook(path)
            ws = wb.active
        else:
            wb = Workbook()
            ws = wb.active
            ws.title = "Runs"
            ws.append(HEADERS)
        for row in rows:
            ws.append(row)
        wb.save(path)
        return path
    except PermissionError:  # file open in Excel on Windows
        pending = path.with_name("pending_log.csv")
        new_file = not pending.exists()
        with pending.open("a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new_file:
                w.writerow(HEADERS)
            w.writerows(rows)
        return pending

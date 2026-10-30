"""Append every run to an Excel log; fall back to CSV if the workbook is open/locked."""
from __future__ import annotations

from pathlib import Path

import pandas as pd


def append_log(cfg: dict, summary) -> Path:
    rows = [
        {
            "run_started": summary.started,
            "report": r.name,
            "status": r.status,
            "file": r.file,
            "error": r.error,
        }
        for r in summary.results
    ]
    new = pd.DataFrame(rows)
    path = Path(cfg["download_root"]) / "Download_Log.xlsx"
    try:
        old = pd.read_excel(path) if path.exists() else pd.DataFrame()
        pd.concat([old, new], ignore_index=True).to_excel(path, index=False)
        return path
    except PermissionError:  # file open in Excel on Windows
        pending = path.with_name("pending_log.csv")
        new.to_csv(pending, mode="a", header=not pending.exists(), index=False)
        return pending

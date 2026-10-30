"""Headless entry point — run once now, or at fixed daily times.

    python scheduler.py --once
    python scheduler.py --at 08:30 --at 17:00

On Windows this can also be called from Task Scheduler with --once.
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime
from pathlib import Path

from agent import run_job

HERE = Path(__file__).parent


def load_config() -> dict:
    path = HERE / "config.json"
    if not path.exists():
        raise SystemExit("config.json not found — copy config.example.json and fill it in.")
    return json.loads(path.read_text())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--at", action="append", default=[], help="HH:MM, repeatable")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    cfg = load_config()

    if args.once or not args.at:
        print(run_job(cfg).overall)
        return

    done_today: set[str] = set()
    while True:
        now = datetime.now()
        key = now.strftime("%Y-%m-%d %H:%M")
        if now.strftime("%H:%M") in args.at and key not in done_today:
            done_today.add(key)
            print(key, run_job(cfg).overall)
        time.sleep(20)


if __name__ == "__main__":
    main()

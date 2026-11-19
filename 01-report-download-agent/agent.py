"""
Report Download Agent — core automation.

Two-phase run:
  Phase 1: trigger generation of EVERY configured report.
  Wait:    give the server time to build them.
  Phase 2: download each report, accepting only history rows created
           after this run's trigger time (so stale files are never picked up).

Selectors are kept in config so the agent can be pointed at a different app
without code changes.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from playwright.sync_api import Locator, Page, sync_playwright

from notifier import send_summary
from report_log import append_log

log = logging.getLogger("agent")


@dataclass
class ReportResult:
    name: str
    status: str = "PENDING"  # TRIGGERED | DOWNLOADED | FAILED
    file: str | None = None
    error: str | None = None


@dataclass
class RunSummary:
    started: datetime
    results: list[ReportResult] = field(default_factory=list)

    @property
    def overall(self) -> str:
        ok = sum(r.status == "DOWNLOADED" for r in self.results)
        if ok == len(self.results):
            return "SUCCESS"
        return "PARTIAL" if ok else "FAILED"


# --------------------------------------------------------------------------
# Robust interaction helpers
# --------------------------------------------------------------------------
def robust_click(target: Locator, label: str) -> None:
    """Click that survives elements the framework marks aria-disabled.

    Some UI libraries wrap buttons inside a header with aria-disabled="true".
    Playwright's actionability checks then refuse a normal click even though
    the button works for a human. Escalate: normal -> force -> DOM event.
    """
    for attempt, how in enumerate(("normal", "force", "dispatch"), start=1):
        try:
            if how == "normal":
                target.click(timeout=5_000)
            elif how == "force":
                target.click(force=True, timeout=5_000)
            else:
                target.dispatch_event("click")
            log.debug("clicked %s via %s", label, how)
            return
        except Exception as exc:  # noqa: BLE001 — we escalate on any failure
            log.debug("click %s attempt %d (%s) failed: %s", label, attempt, how, exc)
    raise RuntimeError(f"Could not click {label}")


def best_effort(fn, label: str) -> None:
    """Run a cleanup step without letting it fail an otherwise good result."""
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        log.warning("cleanup '%s' skipped: %s", label, exc)


# --------------------------------------------------------------------------
# Page steps
# --------------------------------------------------------------------------
def login(page: Page, cfg: dict) -> None:
    s = cfg["selectors"]
    page.goto(cfg["base_url"])
    page.fill(s["username"], cfg["username"])
    page.fill(s["password"], cfg["password"])
    robust_click(page.locator(s["login_button"]), "login")
    page.wait_for_load_state("networkidle")


def report_card(page: Page, cfg: dict, name: str) -> Locator:
    s = cfg["selectors"]
    return page.locator(s["report_card"]).filter(has=page.locator(s["report_title"], has_text=name))


def trigger_report(page: Page, cfg: dict, name: str) -> None:
    s = cfg["selectors"]
    card = report_card(page, cfg, name)
    robust_click(card.locator(s["generate_button"]).first, f"{name}: open filters")
    # The first button expands a filter panel; the panel's button queues the job.
    robust_click(card.locator(s["panel_generate_button"]).last, f"{name}: queue")


def download_report(page: Page, cfg: dict, name: str, since: datetime, out_dir: Path) -> Path:
    s = cfg["selectors"]
    card = report_card(page, cfg, name)
    rows = card.locator(s["history_row"])
    for i in range(rows.count()):
        row = rows.nth(i)
        text = row.locator(s["history_time"]).inner_text().strip()
        try:
            stamp = datetime.strptime(text, cfg["time_format"])
        except ValueError:
            continue  # row still says "Generating..." or similar: not ready yet
        if stamp >= since:
            with page.expect_download(timeout=60_000) as dl:
                robust_click(row.locator(s["download_icon"]), f"{name}: download")
            target = out_dir / f"{safe(name)}_{datetime.now():%H%M%S}.xlsx"
            dl.value.save_as(target)
            best_effort(lambda: robust_click(card.locator(s["close_button"]), "close"), f"{name}: close")
            return target
    raise RuntimeError("No fresh file in history (generation may still be running)")


def safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------
class _AbortRun(Exception):
    """Login or navigation failed: skip the rest but still log and email."""


def run_job(cfg: dict) -> RunSummary:
    summary = RunSummary(started=datetime.now())
    summary.results = [ReportResult(n) for n in cfg["reports"]]
    out_dir = Path(cfg["download_root"]) / datetime.now().strftime("%d-%m-%Y")
    out_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=cfg.get("headless", True))
        page = browser.new_page(accept_downloads=True)
        try:
            try:
                login(page, cfg)
                page.goto(cfg["base_url"].rstrip("/") + cfg["reports_path"])
            except Exception as exc:  # noqa: BLE001 — still log and email the failure
                for r in summary.results:
                    r.status, r.error = "FAILED", f"login/navigation: {exc}"
                raise _AbortRun from exc

            # Phase 1 — trigger everything
            trigger_time = datetime.now() - timedelta(seconds=cfg.get("clock_skew_s", 120))
            for r in summary.results:
                try:
                    trigger_report(page, cfg, r.name)
                    r.status = "TRIGGERED"
                except Exception as exc:  # noqa: BLE001
                    r.status, r.error = "FAILED", f"trigger: {exc}"
            send_summary(cfg, summary, phase="attempted")

            # Wait for the server to build the reports
            log.info("waiting %ss for generation", cfg["post_trigger_wait_s"])
            time.sleep(cfg["post_trigger_wait_s"])
            page.reload()

            # Phase 2 — download only fresh files, with retries
            for r in (x for x in summary.results if x.status == "TRIGGERED"):
                for attempt in range(cfg.get("download_retries", 3)):
                    try:
                        r.file = str(download_report(page, cfg, r.name, trigger_time, out_dir))
                        r.status = "DOWNLOADED"
                        break
                    except Exception as exc:  # noqa: BLE001 — one bad report must not stop the run
                        r.error = str(exc)
                        time.sleep(30)
                        page.reload()
                else:
                    r.status = "FAILED"
        except _AbortRun:
            pass
        finally:
            browser.close()

    append_log(cfg, summary)
    send_summary(cfg, summary, phase="final")
    return summary

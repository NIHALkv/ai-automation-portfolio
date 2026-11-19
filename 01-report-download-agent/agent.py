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

from playwright.sync_api import Locator, Page, TimeoutError as PWTimeout, sync_playwright

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
        if self.results and ok == len(self.results):
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


def launch_browser(p, cfg: dict):
    """Use a browser already on the PC (Edge, then Chrome) so nothing extra needs
    installing; fall back to Playwright's own Chromium if neither is available."""
    headless = cfg.get("headless", True)
    for channel in cfg.get("browser_channels", ["msedge", "chrome", None]):
        try:
            return p.chromium.launch(headless=headless, channel=channel) if channel else p.chromium.launch(headless=headless)
        except Exception as exc:  # noqa: BLE001
            log.debug("browser %s not available: %s", channel or "bundled chromium", exc)
    raise RuntimeError("No browser found. Install Microsoft Edge or Google Chrome.")


def open_session(p, cfg: dict):
    """Return (closeable, page).

    login_mode "password": fresh browser, fill the login form (original behaviour).
    login_mode "sso": a saved browser profile, so the company sign-in (SSO) is
    remembered between runs. The user signs in once in the visible window.
    """
    if cfg.get("login_mode", "password") != "sso":
        browser = launch_browser(p, cfg)
        return browser, browser.new_page(accept_downloads=True)

    profile = cfg.get("profile_dir") or str(Path.home() / ".report_agent_profile")
    Path(profile).mkdir(parents=True, exist_ok=True)
    headless = cfg.get("headless", False)
    last_exc = None
    for channel in cfg.get("browser_channels", ["msedge", "chrome", None]):
        try:
            kwargs = {"headless": headless, "accept_downloads": True}
            if channel:
                kwargs["channel"] = channel
            ctx = p.chromium.launch_persistent_context(profile, **kwargs)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            return ctx, page
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            log.debug("browser %s not available: %s", channel or "bundled chromium", exc)
    raise RuntimeError(f"Could not open a browser (Edge/Chrome): {last_exc}")


def sso_sign_in(page: Page, cfg: dict) -> None:
    """Open the reports page; if SSO sign-in is needed, wait for the user to finish it."""
    s = cfg["selectors"]
    page.goto(cfg["base_url"].rstrip("/") + cfg["reports_path"])
    try:
        page.wait_for_selector(s["report_card"], timeout=15_000)
        log.info("already signed in")
        return
    except PWTimeout:
        pass
    wait_s = cfg.get("sso_wait_s", 300)
    log.info("please sign in with your company account in the browser window (waiting up to %d min)...", wait_s // 60)
    _notify(cfg, "signin_needed", wait_s=wait_s)
    deadline = time.time() + wait_s
    while time.time() < deadline:
        # after SSO the platform may land on its home page, so go back to reports when needed
        if page.locator(s["report_card"]).count() > 0:
            log.info("signed in")
            return
        try:
            url = page.url.lower()
            on_platform = cfg["base_url"].split("//")[-1].split("/")[0].lower() in url
            in_sign_in = any(w in url for w in ("login", "signin", "sign-in", "sso", "auth", "callback", "oauth"))
            if on_platform and not in_sign_in and cfg["reports_path"].lower() not in url:
                page.goto(cfg["base_url"].rstrip("/") + cfg["reports_path"])
        except Exception:  # noqa: BLE001 — page may be mid-redirect
            pass
        page.wait_for_timeout(3_000)
    raise RuntimeError("Sign-in not completed in time")


def discover_reports(page: Page, cfg: dict) -> list[str]:
    """Read the title of every report card on the page (used when no list is given)."""
    s = cfg["selectors"]
    page.wait_for_selector(s["report_card"], timeout=30_000)
    titles = page.locator(s["report_card"]).locator(s["report_title"]).all_inner_texts()
    return [t.strip() for t in titles if t.strip()]


def _notify(cfg: dict, event: str, **data) -> None:
    """Optional progress callback for a UI: cfg["on_progress"](event, data)."""
    cb = cfg.get("on_progress")
    if cb:
        try:
            cb(event, data)
        except Exception:  # noqa: BLE001 — a UI problem must never stop the run
            pass


def run_job(cfg: dict) -> RunSummary:
    summary = RunSummary(started=datetime.now())
    summary.results = [ReportResult(n) for n in cfg.get("reports") or []]
    out_dir = Path(cfg["download_root"]) / datetime.now().strftime("%d-%m-%Y")
    out_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        _notify(cfg, "step", name="signin")
        browser, page = open_session(p, cfg)
        try:
            try:
                if cfg.get("login_mode", "password") == "sso":
                    sso_sign_in(page, cfg)
                else:
                    login(page, cfg)
                    page.goto(cfg["base_url"].rstrip("/") + cfg["reports_path"])
                if not summary.results:  # no list given: download every report on the page
                    summary.results = [ReportResult(n) for n in discover_reports(page, cfg)]
                    log.info("found %d reports: %s", len(summary.results), ", ".join(r.name for r in summary.results))
                _notify(cfg, "reports", names=[r.name for r in summary.results])
            except Exception as exc:  # noqa: BLE001 — still log and email the failure
                if not summary.results:
                    summary.results = [ReportResult("(all reports)")]
                for r in summary.results:
                    r.status, r.error = "FAILED", f"login/navigation: {exc}"
                raise _AbortRun from exc

            # Phase 1 — trigger everything
            _notify(cfg, "step", name="generate")
            trigger_time = datetime.now() - timedelta(seconds=cfg.get("clock_skew_s", 120))
            for r in summary.results:
                try:
                    trigger_report(page, cfg, r.name)
                    r.status = "TRIGGERED"
                except Exception as exc:  # noqa: BLE001
                    r.status, r.error = "FAILED", f"trigger: {exc}"
                _notify(cfg, "report", name=r.name, status=r.status, error=r.error)
            send_summary(cfg, summary, phase="attempted")

            # Wait for the server to build the reports
            log.info("waiting %ss for generation", cfg["post_trigger_wait_s"])
            _notify(cfg, "step", name="wait", seconds=cfg["post_trigger_wait_s"])
            time.sleep(cfg["post_trigger_wait_s"])
            page.reload()

            # Phase 2 — download only fresh files, with retries
            _notify(cfg, "step", name="download")
            for r in (x for x in summary.results if x.status == "TRIGGERED"):
                for attempt in range(cfg.get("download_retries", 3)):
                    try:
                        r.file = str(download_report(page, cfg, r.name, trigger_time, out_dir))
                        r.status = "DOWNLOADED"
                        _notify(cfg, "report", name=r.name, status=r.status, file=r.file)
                        break
                    except Exception as exc:  # noqa: BLE001 — one bad report must not stop the run
                        r.error = str(exc)
                        time.sleep(30)
                        page.reload()
                else:
                    r.status = "FAILED"
                    _notify(cfg, "report", name=r.name, status=r.status, error=r.error)
        except _AbortRun:
            pass
        finally:
            browser.close()

    if summary.results and all(r.status == "FAILED" for r in summary.results) and summary.results[0].error \
            and summary.results[0].error.startswith("login/navigation"):
        _notify(cfg, "report", name=summary.results[0].name, status="FAILED", error=summary.results[0].error)
    append_log(cfg, summary)
    send_summary(cfg, summary, phase="final")
    _notify(cfg, "done", overall=summary.overall)
    return summary

"""
Report Agent: interactive launcher (this is what report_agent.exe runs).

Double-click the .exe and press Enter. A browser opens; sign in with your
company account (SSO) the first time. The sign-in is remembered, so later runs
need no typing at all beyond Enter.

The platform address is built into the .exe at build time (GitHub repo variable
PLATFORM_URL -> built_in.json), so it is never in the code and never asked.
If it isn't built in, the app asks for it once and remembers it.

Advanced: put a config.json next to the .exe to override anything,
e.g. page selectors or "post_trigger_wait_s".
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

APP_NAME = "Report Agent"

# Built-in defaults (same as config.example.json). Selectors match the platform's UI.
DEFAULTS: dict = {
    "base_url": "",
    "reports_path": "/dashboards-reports",
    "login_mode": "sso",
    "sso_wait_s": 300,
    "username": "",
    "password": "",
    "headless": False,
    "reports": [],
    "download_root": str(Path.home() / "Desktop" / "Reports"),
    "post_trigger_wait_s": 120,
    "clock_skew_s": 120,
    "download_retries": 3,
    "time_format": "%d-%m-%Y %H:%M",
    "selectors": {
        "username": "input[name=email]",
        "password": "input[name=password]",
        "login_button": "button[type=submit]",
        "report_card": "app-report-accordion",
        "report_title": "h3",
        "generate_button": "button:has-text('GENERATE REPORT')",
        "panel_generate_button": "button:has-text('GENERATE REPORT')",
        "history_row": ".history-row",
        "history_time": ".history-time",
        "download_icon": "mat-icon:has-text('download')",
        "close_button": "button:has-text('Close')",
    },
    "email": {"enabled": False, "sender": "", "app_password": "", "recipients": []},
}


def app_dir() -> Path:
    """Folder of the .exe (or of this script when run with Python)."""
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent


def settings_path() -> Path:
    base = Path(os.environ.get("APPDATA", Path.home()))
    folder = base / "ReportAgent"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "settings.json"


def deep_merge(base: dict, extra: dict) -> dict:
    out = dict(base)
    for k, v in extra.items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def bundled_file(name: str) -> Path:
    """File packed inside the .exe (PyInstaller unpacks to sys._MEIPASS)."""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / name


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    built_in_file = bundled_file("built_in.json")
    built_in = json.loads(built_in_file.read_text(encoding="utf-8")) if built_in_file.exists() else {}
    sp = settings_path()
    if sp.exists():
        cfg = deep_merge(cfg, json.loads(sp.read_text(encoding="utf-8")))
    cfg = deep_merge(cfg, built_in)  # built-in address always wins over an old saved one
    override = app_dir() / "config.json"
    if override.exists():
        cfg = deep_merge(cfg, json.loads(override.read_text(encoding="utf-8")))
    return cfg


# ---------------------------------------------------------------- prompts
def ask(question: str, default: str = "", required: bool = False) -> str:
    hint = f" [{default}]" if default else ""
    while True:
        answer = input(f"{question}{hint}: ").strip().strip('"')
        if answer:
            return answer
        if default or not required:
            return default
        print("  This is required.")


def ask_settings(cfg: dict) -> dict:
    current = ", ".join(cfg["reports"]) if cfg["reports"] else "ALL"
    names = ask("Reports to download, comma-separated (ALL = every report on the page)", current)
    cfg["reports"] = [] if names.strip().upper() == "ALL" else [n.strip() for n in names.split(",") if n.strip()]
    cfg["download_root"] = ask("Save files in folder", cfg["download_root"], required=True)
    return cfg


def collect_settings(cfg: dict) -> dict:
    first_time = not settings_path().exists()
    if not cfg["base_url"]:  # only when the address isn't built into the .exe
        url = ask("\nPlatform address (e.g. https://yourcompany.platform.com)", required=True)
        cfg["base_url"] = (url if url.startswith("http") else "https://" + url).rstrip("/")

    print(f"\n  Platform : {cfg['base_url']}")
    print(f"  Reports  : {', '.join(cfg['reports']) if cfg['reports'] else 'ALL'}")
    print(f"  Save to  : {cfg['download_root']}\n")
    if first_time:
        print("First run: press Enter to keep these, or type your own.\n")
        return ask_settings(cfg)
    if input("Press Enter to start, or type C to change these settings: ").strip().lower().startswith("c"):
        return ask_settings(cfg)
    return cfg


def save_settings(cfg: dict) -> None:
    """Remember only what the user answered (never passwords)."""
    keep = {k: cfg[k] for k in ("base_url", "reports", "download_root")}
    settings_path().write_text(json.dumps(keep, indent=2), encoding="utf-8")


def open_folder(path: str) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            os.system(f'open "{path}"')
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    print("=" * 60)
    print(f"  {APP_NAME}: download all your platform reports in one go")
    print("=" * 60)
    logging.basicConfig(level=logging.INFO, format="  %(message)s")
    logging.getLogger("notifier").setLevel(logging.WARNING)

    cfg = load_config()
    cfg["profile_dir"] = str(settings_path().parent / "browser-profile")
    cfg = collect_settings(cfg)
    save_settings(cfg)

    from agent import run_job  # imported here so a startup problem is shown, not swallowed

    print("\nStarting... a browser window will open.")
    print("If it asks you to sign in, use your company account (SSO) as usual.")
    print("You only need to do this once; the app remembers the sign-in.")
    print(f"After triggering, it waits {cfg['post_trigger_wait_s']}s for the reports to be built, then downloads them.\n")
    try:
        summary = run_job(cfg)
    except Exception as exc:  # noqa: BLE001
        print(f"\nSomething went wrong: {exc}")
        return 1

    print("\n" + "-" * 60)
    print(f"  RESULT: {summary.overall}")
    print("-" * 60)
    for r in summary.results:
        line = f"  {r.status:<11} {r.name}"
        if r.status != "DOWNLOADED" and r.error:
            line += f"  ({r.error[:80]})"
        print(line)
    print(f"\nFiles saved in: {cfg['download_root']}")
    print(f"Run log: {Path(cfg['download_root']) / 'Download_Log.xlsx'}")
    open_folder(cfg["download_root"])
    return 0 if summary.overall == "SUCCESS" else 2


def crash_log_path() -> Path:
    try:
        return settings_path().parent / "error_log.txt"
    except Exception:  # noqa: BLE001
        return Path.home() / "report_agent_error_log.txt"


if __name__ == "__main__":
    try:
        code = main()
    except KeyboardInterrupt:
        code = 130
    except BaseException:  # noqa: BLE001 — never close silently
        import traceback

        details = traceback.format_exc()
        log_file = crash_log_path()
        try:
            log_file.write_text(details, encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
        print("\n*** The app hit an error and stopped. ***\n")
        print(details)
        print(f"Details saved to: {log_file}")
        print("Please send this message (or a screenshot) to the person who shared the app.")
        code = 1
    if getattr(sys, "frozen", False) and sys.stdin.isatty():
        input("\nPress Enter to close...")
    sys.exit(code)

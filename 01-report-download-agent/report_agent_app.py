"""
Report Agent: interactive launcher (this is what report_agent.exe runs).

Double-click the .exe and answer a few questions. Answers (except the password)
are remembered for next time, so later runs are just: Enter, Enter, password, Enter.

The platform address is built into the .exe at build time (GitHub repo variable
PLATFORM_URL -> built_in.json), so it is never in the code and never asked.
If it isn't built in, the app asks for it once and remembers it.

Advanced: put a config.json next to the .exe to override anything,
e.g. page selectors or "post_trigger_wait_s".
"""
from __future__ import annotations

import getpass
import json
import logging
import os
import sys
from pathlib import Path

from agent import run_job

APP_NAME = "Report Agent"

# Built-in defaults (same as config.example.json). Selectors match the platform's UI.
DEFAULTS: dict = {
    "base_url": "",
    "reports_path": "/dashboards-reports",
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
    built_in = bundled_file("built_in.json")
    if built_in.exists():
        cfg = deep_merge(cfg, json.loads(built_in.read_text(encoding="utf-8")))
    sp = settings_path()
    if sp.exists():
        cfg = deep_merge(cfg, json.loads(sp.read_text(encoding="utf-8")))
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


def ask_yes_no(question: str, default: bool) -> bool:
    hint = "Y/n" if default else "y/N"
    answer = input(f"{question} ({hint}): ").strip().lower()
    return default if not answer else answer.startswith("y")


def ask_secret(question: str) -> str:
    while True:
        if sys.stdin.isatty():
            value = getpass.getpass(f"{question} (hidden while typing): ")
        else:  # answers piped in (automated test)
            value = input(f"{question}: ")
        if value:
            return value
        print("  This is required.")


def collect_settings(cfg: dict) -> dict:
    print("\nPress Enter to keep the value shown in [brackets].\n")
    if not cfg["base_url"]:  # only when the address isn't built into the .exe
        url = ask("Platform address (e.g. https://yourcompany.platform.com)", required=True)
        cfg["base_url"] = (url if url.startswith("http") else "https://" + url).rstrip("/")
    else:
        print(f"Platform: {cfg['base_url']}\n")
    cfg["username"] = ask("1. Login email / username", cfg["username"], required=True)
    cfg["password"] = ask_secret("2. Password")

    current = ", ".join(cfg["reports"]) if cfg["reports"] else "ALL"
    names = ask("3. Reports to download, comma-separated (ALL = every report on the page)", current)
    cfg["reports"] = [] if names.strip().upper() == "ALL" else [n.strip() for n in names.split(",") if n.strip()]

    cfg["download_root"] = ask("4. Save files in folder", cfg["download_root"], required=True)
    cfg["headless"] = not ask_yes_no("5. Show the browser while it works?", not cfg["headless"])

    email = cfg["email"]
    email["enabled"] = ask_yes_no("6. Email a summary when done?", email.get("enabled", False))
    if email["enabled"]:
        email["sender"] = ask("   Gmail address to send from", email.get("sender", ""), required=True)
        email["app_password"] = ask_secret("   Gmail app password (16 characters)")
        email["recipients"] = [
            r.strip()
            for r in ask("   Send to (comma-separated)", ", ".join(email.get("recipients", [])) or email["sender"]).split(",")
            if r.strip()
        ]
    return cfg


def save_settings(cfg: dict) -> None:
    """Remember only what the user answered (never passwords)."""
    keep = {k: cfg[k] for k in ("base_url", "username", "reports", "download_root", "headless")}
    keep["email"] = {k: v for k, v in cfg["email"].items() if k != "app_password"}
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

    cfg = collect_settings(load_config())
    if ask_yes_no("\nRemember these answers for next time? (password is never saved)", True):
        save_settings(cfg)

    print("\nStarting... a browser will open, log in and generate the reports.")
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


if __name__ == "__main__":
    code = main()
    if getattr(sys, "frozen", False) and sys.stdin.isatty():
        input("\nPress Enter to close...")
    sys.exit(code)

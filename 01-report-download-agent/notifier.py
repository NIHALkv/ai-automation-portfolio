"""Email notifications via SMTP (e.g. Gmail with an app password)."""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

log = logging.getLogger("notifier")


def build_body(summary, phase: str) -> tuple[str, str]:
    if phase == "attempted":
        subject = f"[Report Agent] Run started — {len(summary.results)} reports triggered"
    else:
        subject = f"[Report Agent] {summary.overall} — {summary.started:%d %b %Y %H:%M}"
    lines = [f"Run started: {summary.started:%d-%m-%Y %H:%M:%S}", ""]
    for r in summary.results:
        extra = f" — {r.error}" if r.error and r.status == "FAILED" else ""
        lines.append(f"  {r.status:<11} {r.name}{extra}")
    return subject, "\n".join(lines)


def send_summary(cfg: dict, summary, phase: str) -> None:
    subject, body = build_body(summary, phase)
    mail = cfg.get("email", {})
    if not mail.get("enabled") or not mail.get("app_password"):
        log.info("email disabled — would send:\n%s\n%s", subject, body)
        return
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, mail["sender"], ", ".join(mail["recipients"])
    msg.set_content(body)
    with smtplib.SMTP_SSL(mail.get("smtp_host", "smtp.gmail.com"), 465) as s:
        s.login(mail["sender"], mail["app_password"])
        s.send_message(msg)

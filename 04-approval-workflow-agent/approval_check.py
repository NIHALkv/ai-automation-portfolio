"""
Approval Workflow Agent

Checks every demand approval against the offline approver hierarchy and sends
a daily status email: correctly approved, approved by the wrong person, and
pending (with ageing).

    python approval_check.py --dry-run           # print the email, don't send
    python approval_check.py --to me@example.com # send via SMTP (env vars below)

SMTP settings come from env vars: SMTP_USER, SMTP_APP_PASSWORD, SMTP_HOST.
"""
from __future__ import annotations

import argparse
import os
import smtplib
from datetime import date
from email.message import EmailMessage
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
STALE_DAYS = 7


def classify(demands: pd.DataFrame, hierarchy: pd.DataFrame, today: date) -> pd.DataFrame:
    d = demands.merge(hierarchy, on=["business_unit", "practice"], how="left")
    by = d.approved_by.fillna("").str.strip().str.lower()

    d["result"] = "Approved – wrong approver"
    d.loc[d.status.eq("Pending"), "result"] = "Pending"
    d.loc[d.status.eq("Approved") & by.eq(d.approver.str.lower()), "result"] = "Approved – correct"
    d.loc[d.status.eq("Approved") & by.eq(d.backup_approver.str.lower()), "result"] = "Approved – backup approver"
    d.loc[d.approver.isna(), "result"] = "No hierarchy mapping"

    d["age_days"] = (pd.Timestamp(today) - pd.to_datetime(d.raised_on)).dt.days
    return d


def build_email(d: pd.DataFrame, today: date) -> tuple[str, str]:
    counts = d.result.value_counts()
    wrong = d[d.result.eq("Approved – wrong approver")]
    stale = d[d.result.eq("Pending") & (d.age_days > STALE_DAYS)].sort_values("age_days", ascending=False)

    lines = [f"Demand approval status — {today:%d %b %Y}", "", "Summary"]
    lines += [f"  {k:<28} {v}" for k, v in counts.items()]
    lines += ["", f"Approved by the wrong person ({len(wrong)})"]
    lines += [f"  {r.demand_id}  {r.business_unit}/{r.practice}  by {r.approved_by}  (expected {r.approver})"
              for r in wrong.itertuples()] or ["  none"]
    lines += ["", f"Pending more than {STALE_DAYS} days ({len(stale)})"]
    lines += [f"  {r.demand_id}  {r.age_days}d  waiting on {r.approver}" for r in stale.itertuples()] or ["  none"]

    correct = counts.get("Approved – correct", 0) + counts.get("Approved – backup approver", 0)
    subject = f"Approvals {today:%d %b}: {correct} correct, {len(wrong)} wrong approver, {counts.get('Pending', 0)} pending"
    return subject, "\n".join(lines)


def send(subject: str, body: str, to: list[str]) -> None:
    user, pwd = os.environ["SMTP_USER"], os.environ["SMTP_APP_PASSWORD"]
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, user, ", ".join(to)
    msg.set_content(body)
    with smtplib.SMTP_SSL(os.environ.get("SMTP_HOST", "smtp.gmail.com"), 465) as s:
        s.login(user, pwd)
        s.send_message(msg)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=HERE / "sample_data")
    ap.add_argument("--to", action="append", default=[])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--today", type=date.fromisoformat, default=date.today())
    args = ap.parse_args()

    demands = pd.read_csv(args.data / "demand_approvals.csv")
    hierarchy = pd.read_csv(args.data / "approver_hierarchy.csv")
    d = classify(demands, hierarchy, args.today)
    subject, body = build_email(d, args.today)

    out = HERE / "output"
    out.mkdir(exist_ok=True)
    d.to_excel(out / f"approval_check_{args.today:%Y%m%d}.xlsx", index=False)

    if args.dry_run or not args.to:
        print("SUBJECT:", subject, "\n", body, sep="")
    else:
        send(subject, body, args.to)
        print("sent to", ", ".join(args.to))


if __name__ == "__main__":
    main()

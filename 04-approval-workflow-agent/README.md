# 04 · Approval Workflow Agent

A daily check that every demand was approved by the right person.

## Problem
Demands must be approved by the approver for their business unit and practice. The hierarchy lived in an offline sheet, so the platform couldn't enforce it. Wrong-person approvals and long-pending demands were found late, during audits or escalations.

## What it does
- Joins the platform's approval export with the hierarchy sheet on business unit + practice.
- Classifies each demand: **correct**, **backup approver**, **wrong approver**, **pending**, or **no hierarchy mapping**.
- Calculates pending age and flags anything older than 7 days.
- Sends a short daily email with counts, wrong-approver cases and stale items with who they're waiting on.

## Run
```bash
python make_sample_data.py
python approval_check.py --dry-run --today 2026-10-30

# real send (Gmail app password)
set SMTP_USER=you@gmail.com
set SMTP_APP_PASSWORD=xxxx
python approval_check.py --to team@example.com
```
Schedule it daily with Windows Task Scheduler or cron.

## Design notes
- Credentials come from environment variables, never from code or config files in the repo.
- `--dry-run` is the default when no recipient is given, so a first-time user can't spam anyone.
- "No hierarchy mapping" is its own category. It finds gaps in the hierarchy sheet itself, not only in approvals.

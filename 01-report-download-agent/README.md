# 01 · Report Download Agent

An unattended browser agent that downloads every report from a SaaS platform and tells the team how it went.

## Problem
Ops teams needed a fresh set of reports from the platform every day. Each report had to be opened, filtered, generated, waited on and downloaded by hand.

## How it works

```
login → open reports page
  │
  ├─ PHASE 1: trigger ALL reports      → email #1 "run started"
  ├─ wait N seconds for server to build
  └─ PHASE 2: for each report
        download only files stamped after this run's trigger time
        retry up to 3× if not ready
  │
  └─ log to Excel → email #2 SUCCESS / PARTIAL / FAILED
```

Triggering everything first and then downloading cuts total run time. The server builds reports in parallel instead of one at a time.

## Interesting problem I solved
The platform's report cards sit inside a header the UI framework marks `aria-disabled="true"`. A human can click the buttons, but Playwright refuses because it thinks they're disabled. I added `robust_click()`, which escalates **normal click → force click → raw DOM event**.

A second bug: after a successful download, closing the panel sometimes failed. That marked good reports as failed. Cleanup now runs `best_effort()` so it can never override a real result.

## Files
| File | Role |
|------|------|
| `agent.py` | Playwright core: login, trigger, download, orchestration |
| `notifier.py` | SMTP email summaries |
| `report_log.py` | Excel run log, CSV fallback when the workbook is locked |
| `scheduler.py` | Headless CLI: `--once` or `--at 08:30` |
| `webapp.py` | One-button local web UI for teammates |
| `config.example.json` | All URLs, selectors and report names, so no code edits are needed |

## Run
```bash
pip install -r ../requirements.txt && playwright install chromium
cp config.example.json config.json   # fill in URL, login, selectors
python scheduler.py --once           # or: python webapp.py
```
`config.json` is git-ignored so credentials never get committed.

## Next step
Replace hard-coded selectors with an LLM-guided step ("find the Generate button for report X") so the agent survives UI changes.

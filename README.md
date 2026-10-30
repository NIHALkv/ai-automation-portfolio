# AI & Automation Portfolio — Nihal K V

Tools and agents I built while working as an **Implementation / Program Manager at a B2B HR-tech SaaS company**, rolling out a workforce-planning platform for large IT-services clients.

Each project started from a real, repetitive operational problem and turned it into an automated, repeatable check or agent.

> All client names, product names, URLs and data have been removed. Every dataset in this repo is **synthetic** and generated for demonstration.

## Projects

| # | Project | What it does | Tech |
|---|---------|--------------|------|
| 01 | [Report Download Agent](01-report-download-agent/) | Logs into a web platform, triggers every report, waits, downloads only fresh files, logs results and emails a SUCCESS / PARTIAL / FAILED summary. Runs unattended on a schedule. | Python, Playwright, Flask, SMTP |
| 02 | [Bench Reconciliation](02-bench-reconciliation/) | Cross-checks 3 data sources (client staffing, platform allocations, offline bench list) to flag mismatches and people with no allocation. | Python, pandas |
| 03 | [JD Template Checker](03-jd-template-checker/) | Scores job descriptions against a mandatory section template and builds a status matrix. Non-compliant JDs were causing job-request creation to fail. | Python, regex, pandas |
| 04 | [Approval Workflow Agent](04-approval-workflow-agent/) | Checks pending approvals against an approver hierarchy and sends a daily status email. | Python, pandas, SMTP |

## Problem → solution

| Before | After |
|--------|-------|
| Daily manual clicking through every report screen | One scheduled run, email when done |
| Manual VLOOKUPs across 3 spreadsheets to find bench gaps | One command, Excel output with every gap categorised |
| JR creation failing with no clear reason | Every JD scored, missing sections named |
| No visibility on wrong-approver approvals | Daily email with correct / wrong / pending counts |

## Quick start

```bash
git clone https://github.com/NIHALkv/ai-automation-portfolio.git
cd ai-automation-portfolio
pip install -r requirements.txt

# Data tools run on the included synthetic data
python 02-bench-reconciliation/reconcile.py
python 03-jd-template-checker/jd_checker.py
python 04-approval-workflow-agent/approval_check.py --dry-run
```

The report agent needs a target web app; see its README.

## Skills shown

- **Agentic automation:** a browser agent that plans a run, handles flaky UI, retries, and reports outcome.
- **Data quality for AI/ML:** reconciliation and validation are the groundwork any AI system on enterprise data depends on.
- **Text classification:** rule-based section detection in unstructured job descriptions (a baseline I'd next replace with an LLM classifier).
- **Product thinking:** each tool is built around a stakeholder's question, not a script.

## Built with AI assistance

I designed these tools and directed the build, using Claude as a coding partner. I'm comfortable explaining every design choice.

## Contact

[LinkedIn](https://www.linkedin.com/in/nihalkvind/)

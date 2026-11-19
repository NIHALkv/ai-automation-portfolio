"""Mock of the reports platform, mirroring the selectors in config.example.json.

- Login form (email/password/submit)
- Report cards <app-report-accordion> whose header is aria-disabled="true"
- First GENERATE opens a filter panel; panel's GENERATE queues a job
- History rows: an old (stale) file, plus new jobs that show "Generating..."
  until ready, then a timestamp + download icon
- "Broken Report" has no generate button (should FAIL -> PARTIAL run)
- MOCK_SSO=1: unauthenticated users go to a fake SSO page that signs in by
  itself after 3s and lands on /home (tests the SSO wait + return-to-reports)
"""
import io
import os
import sys
import time
from datetime import datetime, timedelta

from flask import Flask, redirect, request, send_file

READY_AFTER = float(sys.argv[2]) if len(sys.argv) > 2 else 3
app = Flask(__name__)
jobs = {}  # name -> list of (created_ts, ready_ts)
REPORTS = ["Allocation Report", "Demand Report", "Skills Report", "Broken Report"]
FMT = "%d-%m-%Y %H:%M"


@app.get("/")
def login_page():
    return """<form method=post action=/login>
    <input name=email><input name=password type=password><button type=submit>Login</button></form>"""


@app.post("/login")
def do_login():
    resp = redirect("/home")
    resp.set_cookie("auth", "ok", max_age=7 * 24 * 3600)  # persistent, like "stay signed in"
    return resp


@app.get("/sso/login")
def sso_login():
    """Simulated company SSO page: signs in by itself after 3 seconds
    (like Microsoft SSO on a company laptop), then lands on the home page."""
    return """<p>Signing you in with your company account...</p>
    <form id=f method=post action=/login></form>
    <script>setTimeout(() => document.getElementById('f').submit(), 3000)</script>"""


@app.get("/home")
def home():
    return "<h1>Home</h1>"


@app.post("/generate")
def generate():
    name = request.args["name"]
    now = time.time()
    jobs.setdefault(name, []).append((now, now + READY_AFTER))
    return "ok"


@app.get("/download")
def download():
    data = io.BytesIO(f"report {request.args['name']} {request.args['ts']}".encode())
    return send_file(data, as_attachment=True, download_name="report.xlsx")


@app.get("/dashboards-reports")
def reports():
    if request.cookies.get("auth") != "ok":
        return redirect("/sso/login" if os.environ.get("MOCK_SSO") else "/")
    cards = []
    stale = (datetime.now() - timedelta(days=1)).strftime(FMT)
    for name in REPORTS:
        rows = [f'<div class=history-row><span class=history-time>{stale}</span>'
                f'<a href="/download?name={name}&ts=old"><mat-icon>download</mat-icon></a></div>']
        for created, ready in reversed(jobs.get(name, [])):
            if time.time() < ready:
                rows.insert(0, '<div class=history-row><span class=history-time>Generating...</span></div>')
            else:
                ts = datetime.fromtimestamp(created).strftime(FMT)
                rows.insert(0, f'<div class=history-row><span class=history-time>{ts}</span>'
                               f'<a href="/download?name={name}&ts={created}"><mat-icon>download</mat-icon></a></div>')
        gen = '' if name == "Broken Report" else '<button onclick="this.closest(\'app-report-accordion\').querySelector(\'.panel\').hidden=false">GENERATE REPORT</button>'
        panel_btn = '' if name == "Broken Report" else f'<button onclick="fetch(\'/generate?name={name}\',{{method:\'POST\'}})">GENERATE REPORT</button>'
        cards.append(f"""<app-report-accordion>
  <div class=header aria-disabled="true" role="button"><h3>{name}</h3>{gen}</div>
  <div class=panel hidden>{panel_btn}<button>Close</button></div>
  <div class=history>{''.join(rows)}</div>
</app-report-accordion>""")
    return "<h1>Reports</h1>" + "\n".join(cards)


if __name__ == "__main__":
    app.run(port=int(sys.argv[1]) if len(sys.argv) > 1 else 5055)

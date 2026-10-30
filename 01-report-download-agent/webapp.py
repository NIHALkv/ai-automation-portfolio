"""Small local web UI so non-technical teammates can start a run with one click.

    python webapp.py   ->  http://localhost:8765
"""
from __future__ import annotations

import logging
import threading

from flask import Flask, jsonify, render_template_string

from agent import run_job
from scheduler import load_config

app = Flask(__name__)
state = {"running": False, "last": None}

PAGE = """
<!doctype html><title>Report Agent</title>
<style>body{font-family:system-ui;max-width:640px;margin:40px auto;padding:0 16px}
button{padding:10px 18px;font-size:16px}pre{background:#f4f4f4;padding:12px}</style>
<h1>Report Download Agent</h1>
<p>Reports configured: {{ reports|length }}</p>
<button onclick="fetch('/run',{method:'POST'}).then(()=>poll())">Run now</button>
<pre id=out>Idle</pre>
<script>
function poll(){fetch('/status').then(r=>r.json()).then(s=>{
 out.textContent = s.running ? 'Running…' : JSON.stringify(s.last,null,2);
 if(s.running) setTimeout(poll,3000);});}
poll();
</script>
"""


@app.get("/")
def index():
    return render_template_string(PAGE, reports=load_config()["reports"])


@app.post("/run")
def run():
    if state["running"]:
        return jsonify(error="already running"), 409

    def work():
        state["running"] = True
        try:
            s = run_job(load_config())
            state["last"] = {"overall": s.overall, "reports": [r.__dict__ for r in s.results]}
        finally:
            state["running"] = False

    threading.Thread(target=work, daemon=True).start()
    return jsonify(ok=True)


@app.get("/status")
def status():
    return jsonify(state)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(port=8765)

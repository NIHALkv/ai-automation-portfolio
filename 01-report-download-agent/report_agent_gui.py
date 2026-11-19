"""
Report Downloader: desktop app (this is what report_agent.exe runs).

A branded window, no command prompt:
  1. Choose ALL reports (or name a few) and where to save them.
  2. Click "Download reports".
  3. A browser opens. Sign in with your company account (SSO) the first time;
     the sign-in is remembered.
  4. Watch each step and each report's status live, then open the folder.
"""
from __future__ import annotations

import logging
import os
import queue
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox, simpledialog, ttk

from report_agent_app import bundled_file, load_config, save_settings, settings_path

# ---------------------------------------------------------------- brand tokens (PF design kit)
NAVY = "#001453"          # on-primary-container
PRIMARY = "#1f40cb"       # primary
PRIMARY_DARK = "#0933c1"  # on-primary-fixed-variant (hover)
ON_PRIMARY = "#ffffff"
SURFACE = "#f7f9ff"       # surface
CARD = "#ffffff"          # surface-container-lowest
TINT = "#ecf4ff"          # surface-container-low
TEXT = "#191c20"          # on-surface
MUTED = "#43474e"         # on-surface-variant
LINE = "#c3c7cf"          # outline-variant
OK = "#16a34a"            # viz-green (status only)
WARN = "#b45309"          # risk-medium (status only)
BAD = "#dc2626"           # viz-red (status only)

STEPS = [("signin", "Sign in"), ("generate", "Generate"), ("wait", "Wait"), ("download", "Download")]
STATUS_TEXT = {
    "PENDING": "Waiting",
    "TRIGGERED": "Generating…",
    "DOWNLOADED": "Downloaded",
    "FAILED": "Failed",
}


def load_brand_font() -> None:
    """Register the bundled Plus Jakarta Sans for this app only (Windows)."""
    ttf = bundled_file("branding/PlusJakartaSans.ttf")
    if sys.platform.startswith("win") and ttf.exists():
        try:
            import ctypes

            ctypes.windll.gdi32.AddFontResourceExW(str(ttf), 0x10, 0)  # FR_PRIVATE
        except Exception:  # noqa: BLE001
            pass


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.events: queue.Queue = queue.Queue()
        self.running = False
        self.cfg = load_config()
        self.cfg["profile_dir"] = str(settings_path().parent / "browser-profile")
        self.wait_until = 0.0
        self.total = 0
        self.finished = 0
        self.exit_code = 0

        root.title("Prismforce · Report Downloader")
        root.configure(bg=SURFACE)
        root.geometry("760x800")
        root.minsize(680, 640)
        try:
            root.iconbitmap(default=str(bundled_file("branding/pf-icon.ico")))
        except Exception:  # noqa: BLE001
            try:
                self._icon = tk.PhotoImage(file=str(bundled_file("branding/pf-mark.png")))
                root.iconphoto(True, self._icon)
            except Exception:  # noqa: BLE001
                pass

        families = set(tkfont.families(root))
        face = "Plus Jakarta Sans" if "Plus Jakarta Sans" in families else ("Segoe UI" if "Segoe UI" in families else "Helvetica")
        self.f_title = (face, 17, "bold")
        self.f_h = (face, 11, "bold")
        self.f_body = (face, 10)
        self.f_small = (face, 9)
        self.f_btn = (face, 11, "bold")

        self._styles(face)
        self._header()
        self._body()
        self.root.after(100, self._poll)
        if os.environ.get("REPORT_AGENT_AUTOSTART"):  # used by the automated Windows test
            self.root.after(800, self.start)

    # ------------------------------------------------------------ layout
    def _styles(self, face: str) -> None:
        st = ttk.Style(self.root)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure("PF.Horizontal.TProgressbar", troughcolor=TINT, background=PRIMARY,
                     bordercolor=TINT, lightcolor=PRIMARY, darkcolor=PRIMARY, thickness=8)
        st.configure("PF.Treeview", background=CARD, fieldbackground=CARD, foreground=TEXT,
                     rowheight=28, font=(face, 10), borderwidth=0)
        st.configure("PF.Treeview.Heading", background=TINT, foreground=MUTED, font=(face, 9, "bold"),
                     relief="flat", borderwidth=0)
        st.map("PF.Treeview", background=[("selected", TINT)], foreground=[("selected", TEXT)])
        st.configure("PF.TRadiobutton", background=CARD, foreground=TEXT, font=(face, 10))
        st.map("PF.TRadiobutton", background=[("active", CARD)])

    def _header(self) -> None:
        bar = tk.Frame(self.root, bg=NAVY, height=64)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        try:
            img = tk.PhotoImage(file=str(bundled_file("branding/logo-on-dark.png")))
            self._logo = img.subsample(3, 3)  # 498x92 -> 166x31, aspect ratio kept
            tk.Label(bar, image=self._logo, bg=NAVY).pack(side="left", padx=20)
        except Exception:  # noqa: BLE001
            tk.Label(bar, text="Prismforce", bg=NAVY, fg=ON_PRIMARY, font=self.f_h).pack(side="left", padx=20)
        tk.Label(bar, text="Report Downloader", bg=NAVY, fg=ON_PRIMARY, font=self.f_h).pack(side="right", padx=20)

    def _card(self, parent: tk.Widget) -> tk.Frame:
        outer = tk.Frame(parent, bg=LINE)
        inner = tk.Frame(outer, bg=CARD, padx=18, pady=14)
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        return outer, inner

    def _body(self) -> None:
        body = tk.Frame(self.root, bg=SURFACE, padx=24, pady=18)
        body.pack(fill="both", expand=True)

        tk.Label(body, text="Download your platform reports", bg=SURFACE, fg=TEXT, font=self.f_title,
                 anchor="w").pack(fill="x")
        tk.Label(body, text="Signs in with your company account, generates every report, and saves fresh copies.",
                 bg=SURFACE, fg=MUTED, font=self.f_body, anchor="w").pack(fill="x", pady=(2, 14))

        # ---- settings card
        outer, card = self._card(body)
        outer.pack(fill="x")
        card.columnconfigure(1, weight=1)

        tk.Label(card, text="Platform", bg=CARD, fg=MUTED, font=self.f_small).grid(row=0, column=0, sticky="w", pady=4)
        self.platform_lbl = tk.Label(card, text=self._platform_text(), bg=CARD, fg=TEXT, font=self.f_body, anchor="w")
        self.platform_lbl.grid(row=0, column=1, columnspan=2, sticky="w", padx=(12, 0))

        tk.Label(card, text="Reports", bg=CARD, fg=MUTED, font=self.f_small).grid(row=1, column=0, sticky="nw", pady=6)
        rp = tk.Frame(card, bg=CARD)
        rp.grid(row=1, column=1, columnspan=2, sticky="we", padx=(12, 0), pady=4)
        self.mode = tk.StringVar(value="all" if not self.cfg["reports"] else "some")
        ttk.Radiobutton(rp, text="All reports on the page", variable=self.mode, value="all",
                        style="PF.TRadiobutton", command=self._toggle_names).pack(anchor="w")
        row = tk.Frame(rp, bg=CARD)
        row.pack(fill="x", pady=(4, 0))
        ttk.Radiobutton(row, text="Only these:", variable=self.mode, value="some",
                        style="PF.TRadiobutton", command=self._toggle_names).pack(side="left")
        self.names = tk.Entry(row, font=self.f_body, relief="solid", bd=1, highlightthickness=0, fg=TEXT)
        self.names.insert(0, ", ".join(self.cfg["reports"]))
        self.names.pack(side="left", fill="x", expand=True, padx=(8, 0), ipady=4)
        tk.Label(rp, text="Separate names with commas, exactly as shown on the reports page.",
                 bg=CARD, fg=MUTED, font=self.f_small).pack(anchor="w", pady=(2, 0))
        self._toggle_names()

        tk.Label(card, text="Save to", bg=CARD, fg=MUTED, font=self.f_small).grid(row=2, column=0, sticky="w", pady=6)
        self.folder = tk.Entry(card, font=self.f_body, relief="solid", bd=1, highlightthickness=0, fg=TEXT)
        self.folder.insert(0, self.cfg["download_root"])
        self.folder.grid(row=2, column=1, sticky="we", padx=(12, 8), ipady=4)
        self._button(card, "Browse…", self._browse, primary=False).grid(row=2, column=2, sticky="e")

        # ---- actions
        actions = tk.Frame(body, bg=SURFACE)
        actions.pack(fill="x", pady=16)
        self.start_btn = self._button(actions, "Download reports", self.start, primary=True, big=True)
        self.start_btn.pack(side="left")
        self.open_btn = self._button(actions, "Open folder", self._open_folder, primary=False, big=True)
        self.open_btn.pack(side="left", padx=10)
        tk.Label(actions, text="A browser window opens. Sign in with your\ncompany account the first time.",
                 bg=SURFACE, fg=MUTED, font=self.f_small, justify="left").pack(side="left", padx=8)

        # ---- progress card
        outer, prog = self._card(body)
        outer.pack(fill="both", expand=True)

        stepper = tk.Frame(prog, bg=CARD)
        stepper.pack(fill="x")
        self.step_labels = {}
        for i, (key, label) in enumerate(STEPS):
            cell = tk.Frame(stepper, bg=CARD)
            cell.pack(side="left", expand=True, fill="x")
            dot = tk.Label(cell, text=str(i + 1), bg=TINT, fg=MUTED, font=self.f_h, width=3)
            dot.pack()
            txt = tk.Label(cell, text=label, bg=CARD, fg=MUTED, font=self.f_small)
            txt.pack(pady=(4, 0))
            self.step_labels[key] = (dot, txt, i + 1)

        self.status = tk.Label(prog, text="Ready when you are.", bg=CARD, fg=TEXT, font=self.f_body,
                               anchor="w", justify="left")
        self.status.pack(fill="x", pady=(14, 6))
        self.bar = ttk.Progressbar(prog, style="PF.Horizontal.TProgressbar", mode="determinate", maximum=100)
        self.bar.pack(fill="x")

        table = tk.Frame(prog, bg=CARD)
        table.pack(fill="both", expand=True, pady=(12, 0))
        self.tree = ttk.Treeview(table, columns=("status",), show="tree headings", style="PF.Treeview", height=6)
        self.tree.heading("#0", text="REPORT", anchor="w")
        self.tree.heading("status", text="STATUS", anchor="w")
        self.tree.column("#0", stretch=True, width=420)
        self.tree.column("status", width=200, anchor="w")
        for tag, color in (("ok", OK), ("bad", BAD), ("busy", PRIMARY), ("idle", MUTED)):
            self.tree.tag_configure(tag, foreground=color)
        sb = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self.result = tk.Label(body, text="", bg=SURFACE, fg=TEXT, font=self.f_h, anchor="w")
        self.result.pack(fill="x", pady=(10, 0))

    def _button(self, parent, text, cmd, primary=True, big=False) -> tk.Button:
        bg, fg, hover = (PRIMARY, ON_PRIMARY, PRIMARY_DARK) if primary else (CARD, PRIMARY, TINT)
        b = tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg, activebackground=hover, activeforeground=fg,
                      font=self.f_btn if big else self.f_body, relief="flat", bd=0, cursor="hand2",
                      padx=18 if big else 12, pady=9 if big else 5,
                      highlightthickness=0 if primary else 1, highlightbackground=LINE)
        b.bind("<Enter>", lambda e: b.config(bg=hover) if b["state"] != "disabled" else None)
        b.bind("<Leave>", lambda e: b.config(bg=bg) if b["state"] != "disabled" else None)
        b._pf_colors = (bg, fg)  # noqa: SLF001
        return b

    # ------------------------------------------------------------ helpers
    def _platform_text(self) -> str:
        url = self.cfg.get("base_url") or ""
        return url.replace("https://", "").replace("http://", "") or "not set (you'll be asked once)"

    def _toggle_names(self) -> None:
        self.names.config(state="normal" if self.mode.get() == "some" else "disabled",
                          disabledbackground=TINT)

    def _browse(self) -> None:
        d = filedialog.askdirectory(initialdir=self.folder.get() or str(Path.home()), title="Save reports in…")
        if d:
            self.folder.delete(0, "end")
            self.folder.insert(0, d)

    def _open_folder(self) -> None:
        path = self.folder.get().strip()
        Path(path).mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                os.system(f'open "{path}"')
            else:
                os.system(f'xdg-open "{path}" >/dev/null 2>&1 &')
        except Exception:  # noqa: BLE001
            pass

    def _set_step(self, active: str) -> None:
        keys = [k for k, _ in STEPS]
        idx = keys.index(active) if active in keys else len(keys)
        for i, k in enumerate(keys):
            dot, txt, num = self.step_labels[k]
            if i < idx:
                dot.config(text="✓", bg=OK, fg=ON_PRIMARY)
                txt.config(fg=TEXT)
            elif i == idx:
                dot.config(text=str(num), bg=PRIMARY, fg=ON_PRIMARY)
                txt.config(fg=PRIMARY)
            else:
                dot.config(text=str(num), bg=TINT, fg=MUTED)
                txt.config(fg=MUTED)

    def _set_row(self, name: str, status: str, detail: str = "") -> None:
        tag = {"DOWNLOADED": "ok", "FAILED": "bad", "TRIGGERED": "busy"}.get(status, "idle")
        text = STATUS_TEXT.get(status, status)
        if status == "FAILED" and detail:
            text = f"Failed: {detail[:40]}"
        if not self.tree.exists(name):
            self.tree.insert("", "end", iid=name, text=name, values=(text,), tags=(tag,))
        else:
            self.tree.item(name, values=(text,), tags=(tag,))

    def _enable(self, on: bool) -> None:
        for b in (self.start_btn,):
            bg, fg = b._pf_colors  # noqa: SLF001
            b.config(state="normal" if on else "disabled", bg=bg if on else LINE,
                     text="Download reports" if on else "Working…")

    # ------------------------------------------------------------ run
    def start(self) -> None:
        if self.running:
            return
        if not self.cfg.get("base_url"):
            url = simpledialog.askstring("Platform address", "Platform address (e.g. https://yourcompany.platform.com):",
                                         parent=self.root)
            if not url:
                return
            self.cfg["base_url"] = (url if url.startswith("http") else "https://" + url).rstrip("/")
            self.platform_lbl.config(text=self._platform_text())

        if self.mode.get() == "some":
            names = [n.strip() for n in self.names.get().split(",") if n.strip()]
            if not names:
                messagebox.showwarning("Reports", "Type at least one report name, or choose 'All reports'.")
                return
            self.cfg["reports"] = names
        else:
            self.cfg["reports"] = []
        folder = self.folder.get().strip()
        if not folder:
            messagebox.showwarning("Save to", "Choose a folder to save the reports in.")
            return
        self.cfg["download_root"] = folder
        try:
            save_settings(self.cfg)
        except Exception:  # noqa: BLE001
            pass

        self.tree.delete(*self.tree.get_children())
        for n in self.cfg["reports"]:
            self._set_row(n, "PENDING")
        self.total = len(self.cfg["reports"])
        self.finished = 0
        self.bar.config(mode="indeterminate")
        self.bar.start(12)
        self.result.config(text="")
        self._set_step("signin")
        self.status.config(text="Opening the browser…")
        self.running = True
        self._enable(False)

        cfg = dict(self.cfg)
        cfg["on_progress"] = lambda ev, data: self.events.put((ev, data))
        threading.Thread(target=self._work, args=(cfg,), daemon=True).start()

    def _work(self, cfg: dict) -> None:
        try:
            from agent import run_job

            summary = run_job(cfg)
            self.events.put(("finished", {"overall": summary.overall}))
        except Exception as exc:  # noqa: BLE001
            self.events.put(("crashed", {"error": str(exc)}))

    def _poll(self) -> None:
        try:
            while True:
                ev, data = self.events.get_nowait()
                self._handle(ev, data)
        except queue.Empty:
            pass
        if self.wait_until:
            left = int(self.wait_until - time.time())
            if left > 0:
                self.status.config(text=f"Reports are being built on the server… {left // 60}:{left % 60:02d} left")
            else:
                self.wait_until = 0
        self.root.after(250, self._poll)

    def _progress(self) -> None:
        if self.total:
            self.bar.stop()
            self.bar.config(mode="determinate", value=100 * self.finished / self.total)

    def _handle(self, ev: str, data: dict) -> None:
        if ev == "signin_needed":
            self.status.config(text="Please sign in with your company account in the browser window.\n"
                                    f"The app waits up to {data.get('wait_s', 300) // 60} minutes.")
        elif ev == "reports":
            names = data["names"]
            self.tree.delete(*self.tree.get_children())
            for n in names:
                self._set_row(n, "PENDING")
            self.total = len(names)
            self.status.config(text=f"Signed in. Found {len(names)} report(s).")
        elif ev == "step":
            self._set_step(data["name"])
            if data["name"] == "generate":
                self.status.config(text="Starting report generation…")
            elif data["name"] == "wait":
                self.wait_until = time.time() + int(data.get("seconds", 0))
            elif data["name"] == "download":
                self.wait_until = 0
                self.status.config(text="Downloading fresh files…")
                self._progress()
        elif ev == "report":
            self._set_row(data["name"], data["status"], data.get("error") or "")
            if data["status"] in ("DOWNLOADED", "FAILED") and self.tree.exists(data["name"]):
                self.finished = sum(1 for i in self.tree.get_children()
                                    if self.tree.item(i, "values")[0].startswith(("Downloaded", "Failed")))
                self._progress()
        elif ev == "finished":
            self._finish(data["overall"])
        elif ev == "crashed":
            self._finish("FAILED", error=data["error"])

    def _finish(self, overall: str, error: str = "") -> None:
        self.running = False
        self.wait_until = 0
        self.bar.stop()
        self.bar.config(mode="determinate", value=100)
        self._enable(True)
        self._set_step("done")
        ok = sum(1 for i in self.tree.get_children() if self.tree.item(i, "values")[0] == "Downloaded")
        if overall == "SUCCESS":
            self.result.config(text=f"✓  All done: {ok} report(s) downloaded.", fg=OK)
        elif overall == "PARTIAL":
            self.result.config(text=f"!  Partly done: {ok} of {len(self.tree.get_children())} downloaded. "
                                    "See the failed rows above.", fg=WARN)
        else:
            self.result.config(text="✕  Nothing was downloaded." + (f" {error[:90]}" if error else ""), fg=BAD)
        self.status.config(text=f"Saved in {self.cfg['download_root']} (run log: Download_Log.xlsx)")
        self.exit_code = {"SUCCESS": 0, "PARTIAL": 2}.get(overall, 1)
        if os.environ.get("REPORT_AGENT_AUTOSTART") == "1":  # automated test: close when done
            self.root.after(500, self.root.destroy)
        elif ok:
            self._open_folder()


def main() -> int:
    # A windowed .exe has no console: send output to a log file next to the settings
    if sys.stdout is None or sys.stderr is None:
        log_file = open(settings_path().parent / "app_log.txt", "a", encoding="utf-8", buffering=1)  # noqa: SIM115
        sys.stdout = sys.stdout or log_file
        sys.stderr = sys.stderr or log_file
    load_brand_font()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    root = tk.Tk()
    app = App(root)
    root.mainloop()
    return app.exit_code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 — a windowed app must never fail silently
        import traceback

        details = traceback.format_exc()
        try:
            (settings_path().parent / "error_log.txt").write_text(details, encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
        try:
            messagebox.showerror("Report Downloader", f"The app hit an error:\n\n{exc}\n\nDetails saved to "
                                                      f"{settings_path().parent / 'error_log.txt'}")
        except Exception:  # noqa: BLE001
            pass
        sys.exit(1)

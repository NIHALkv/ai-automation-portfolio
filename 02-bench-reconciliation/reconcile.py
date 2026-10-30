"""
Bench reconciliation: compare three views of who is on bench and who is allocated.

  1. client_staffing.csv       — client HR system (source of truth)
  2. platform_allocations.csv  — what was loaded into our platform
  3. bench_list.csv            — offline bench sheet kept by the resourcing team
  + platform_users.csv         — to find users with no allocation at all

Business rule: org unit "Boot Camp" with WBS type BN is a training allocation,
not bench, so it is excluded from bench comparisons.

    python reconcile.py [--data DIR] [--out FILE.xlsx]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent


def latest(folder: Path, stem: str) -> Path:
    """Pick the newest file matching a stem — inputs are re-downloaded daily."""
    hits = sorted(folder.glob(f"{stem}*.csv")) + sorted(folder.glob(f"{stem}*.xlsx"))
    if not hits:
        raise SystemExit(f"No input file starting with '{stem}' in {folder}")
    return max(hits, key=lambda p: p.stat().st_mtime)


def read(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path) if path.suffix == ".csv" else pd.read_excel(path)
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    df["emp_id"] = df["emp_id"].astype(str).str.strip().str.upper()
    return df


def client_expected(client: pd.DataFrame) -> pd.DataFrame:
    c = client.copy()
    is_bootcamp = (c.org_unit == "Boot Camp") & (c.wbs_type == "BN")
    c["expected"] = "Billable"
    c.loc[c.wbs_type == "BN", "expected"] = "Bench"
    c.loc[is_bootcamp, "expected"] = "Training"
    c["expected_project"] = c["project"].fillna("")
    return c


def reconcile(data: Path) -> dict[str, pd.DataFrame]:
    client = client_expected(read(latest(data, "client_staffing")))
    plat = read(latest(data, "platform_allocations"))
    bench = read(latest(data, "bench_list"))
    users = read(latest(data, "platform_users"))

    m = client.merge(plat, on="emp_id", how="left", indicator=True)
    out: dict[str, pd.DataFrame] = {}

    out["Missing on platform"] = m[m._merge == "left_only"][["emp_id", "name", "org_unit", "expected"]]

    both = m[m._merge == "both"]
    out["Bench shown as billable"] = both[(both.expected == "Bench") & (both.allocation_type == "Billable")][
        ["emp_id", "name", "project_y"]].rename(columns={"project_y": "platform_project"})
    out["Wrong project"] = both[(both.expected == "Billable") & (both.project_x != both.project_y)][
        ["emp_id", "name", "project_x", "project_y"]].rename(
        columns={"project_x": "client_project", "project_y": "platform_project"})

    client_bench = set(client.loc[client.expected == "Bench", "emp_id"])
    sheet_bench = set(bench.emp_id)
    out["Bench, not on bench sheet"] = client[client.emp_id.isin(client_bench - sheet_bench)][["emp_id", "name", "org_unit"]]
    out["On bench sheet, but billable"] = client[client.emp_id.isin(sheet_bench - client_bench)
                                                 & (client.expected == "Billable")][["emp_id", "name", "project"]]

    allocated = set(plat.emp_id)
    out["Users without allocation"] = users[users.active & ~users.emp_id.isin(allocated)][["emp_id", "name"]]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=HERE / "sample_data")
    ap.add_argument("--out", type=Path, default=HERE / "output" / "bench_reconciliation.xlsx")
    args = ap.parse_args()

    gaps = reconcile(args.data)
    summary = pd.DataFrame({"gap": list(gaps), "count": [len(v) for v in gaps.values()]})

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(args.out) as xw:
        summary.to_excel(xw, sheet_name="Summary", index=False)
        for name, df in gaps.items():
            df.to_excel(xw, sheet_name=name[:31], index=False)

    print(summary.to_string(index=False))
    print(f"\nDetail written to {args.out}")


if __name__ == "__main__":
    main()

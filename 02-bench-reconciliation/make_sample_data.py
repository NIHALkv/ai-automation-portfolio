"""Generate synthetic input files with deliberately planted gaps.

    python make_sample_data.py   ->  sample_data/*.csv
"""
from __future__ import annotations

import random
from pathlib import Path

import pandas as pd

random.seed(7)
OUT = Path(__file__).parent / "sample_data"
OUT.mkdir(exist_ok=True)

FIRST = ["Asha", "Ravi", "Meera", "Arjun", "Divya", "Kiran", "Neha", "Vikram", "Priya", "Rahul",
         "Sneha", "Anil", "Lakshmi", "Manoj", "Pooja", "Suresh", "Kavya", "Deepak", "Anu", "Rohan"]
LAST = ["Nair", "Menon", "Iyer", "Rao", "Shah", "Pillai", "Das", "Kumar", "Reddy", "Joshi"]
PROJECTS = ["PRJ-101", "PRJ-102", "PRJ-205", "PRJ-310", "PRJ-412"]
UNITS = ["Digital Eng", "Cloud Infra", "Data & AI", "Boot Camp"]

N = 120
emps = [f"E{1000 + i}" for i in range(N)]
names = [f"{random.choice(FIRST)} {random.choice(LAST)}" for _ in emps]

# Client staffing (source of truth from the client's HR system)
staff = []
for e, n in zip(emps, names):
    unit = random.choices(UNITS, weights=[4, 3, 3, 1])[0]
    if unit == "Boot Camp":
        staff.append((e, n, unit, "BN", "", "Bench"))
    elif random.random() < 0.18:
        staff.append((e, n, unit, "BN", "", "Bench"))
    else:
        staff.append((e, n, unit, "BL", random.choice(PROJECTS), "Billable"))
client = pd.DataFrame(staff, columns=["emp_id", "name", "org_unit", "wbs_type", "project", "status"])

# Platform allocations — copy of client data with planted errors
plat = client[client.status == "Billable"][["emp_id", "project"]].copy()
plat["allocation_type"] = "Billable"
bench_on_platform = client[(client.status == "Bench") & (client.org_unit != "Boot Camp")][["emp_id"]].copy()
bench_on_platform["project"] = "BENCH"
bench_on_platform["allocation_type"] = "Bench"
bootcamp = client[client.org_unit == "Boot Camp"][["emp_id"]].copy()
bootcamp["project"] = "BOOTCAMP"
bootcamp["allocation_type"] = "Training"  # rule: Boot Camp + BN loads as Training, not Bench
plat = pd.concat([plat, bench_on_platform, bootcamp], ignore_index=True)

drop = plat.sample(6, random_state=1).index                       # missing on platform
plat = plat.drop(drop)
wrong = plat[plat.allocation_type == "Billable"].sample(4, random_state=2).index
plat.loc[wrong, "project"] = "PRJ-999"                              # wrong project
flip = plat[plat.allocation_type == "Bench"].sample(3, random_state=3).index
plat.loc[flip, ["project", "allocation_type"]] = ["PRJ-102", "Billable"]  # bench shown as billable

# Offline bench list maintained by the resourcing team
bench = client[(client.status == "Bench") & (client.org_unit != "Boot Camp")][["emp_id", "name"]]
bench = bench.drop(bench.sample(3, random_state=4).index)           # forgotten on the sheet
extra = client[client.status == "Billable"].sample(2, random_state=5)[["emp_id", "name"]]
bench = pd.concat([bench, extra])                                    # stale entries

# Platform user list (includes a few users nobody allocated)
users = client[["emp_id", "name"]].copy()
users["active"] = True
ghosts = pd.DataFrame({"emp_id": ["E9001", "E9002", "E9003"],
                       "name": ["Test User", "Anita Varma", "Joseph Mathew"], "active": True})
users = pd.concat([users, ghosts])

client.to_csv(OUT / "client_staffing.csv", index=False)
plat.to_csv(OUT / "platform_allocations.csv", index=False)
bench.to_csv(OUT / "bench_list.csv", index=False)
users.to_csv(OUT / "platform_users.csv", index=False)
print("wrote", *sorted(p.name for p in OUT.glob("*.csv")))

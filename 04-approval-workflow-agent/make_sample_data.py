"""Generate a synthetic approver hierarchy and demand approval export."""
from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

random.seed(3)
OUT = Path(__file__).parent / "sample_data"
OUT.mkdir(exist_ok=True)

hierarchy = pd.DataFrame([
    ("Banking", "Digital Eng", "anita.r@example.com", "suresh.m@example.com"),
    ("Banking", "Data & AI", "kiran.p@example.com", "suresh.m@example.com"),
    ("Insurance", "Digital Eng", "meera.n@example.com", "vikram.s@example.com"),
    ("Insurance", "Cloud Infra", "rahul.d@example.com", "vikram.s@example.com"),
    ("Travel", "Data & AI", "divya.i@example.com", "lakshmi.k@example.com"),
    ("Travel", "Cloud Infra", "arjun.j@example.com", "lakshmi.k@example.com"),
], columns=["business_unit", "practice", "approver", "backup_approver"])

all_people = list(hierarchy.approver) + list(hierarchy.backup_approver) + ["someone.else@example.com"]
rows = []
today = date(2026, 10, 30)
for i in range(60):
    h = hierarchy.sample(1, random_state=i).iloc[0]
    status = random.choices(["Approved", "Pending"], weights=[3, 2])[0]
    if status == "Approved":
        by = random.choices([h.approver, h.backup_approver, random.choice(all_people)], weights=[7, 2, 2])[0]
    else:
        by = ""
    rows.append({
        "demand_id": f"DM-{7000 + i}",
        "business_unit": h.business_unit,
        "practice": h.practice,
        "status": status,
        "approved_by": by,
        "raised_on": (today - timedelta(days=random.randint(0, 20))).isoformat(),
    })

hierarchy.to_csv(OUT / "approver_hierarchy.csv", index=False)
pd.DataFrame(rows).to_csv(OUT / "demand_approvals.csv", index=False)
print("wrote sample_data/approver_hierarchy.csv, demand_approvals.csv")

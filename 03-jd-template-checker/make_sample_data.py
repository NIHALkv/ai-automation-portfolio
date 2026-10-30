"""Generate synthetic job demands with JDs in and out of the required template."""
from __future__ import annotations

import random
from pathlib import Path

import pandas as pd

random.seed(11)
OUT = Path(__file__).parent / "sample_data"
OUT.mkdir(exist_ok=True)

ROLES = [("Java Developer", "Java, Spring Boot, REST APIs", "Kafka, AWS"),
         ("Data Engineer", "Python, SQL, Spark", "Airflow, Databricks"),
         ("QA Analyst", "Selenium, test planning", "Playwright, JMeter"),
         ("Cloud Architect", "AWS, Terraform, networking", "Kubernetes"),
         ("Business Analyst", "Requirements, SQL, stakeholder mgmt", "Power BI")]
STATUSES = ["Migrated", "Post go-live JR created", "Internal"]


def full_jd(role, must, nice, years):
    return (f"Role Summary:\nWe are looking for a {role}.\n\n"
            f"Key Responsibilities:\n- Deliver features\n- Work with the client team\n\n"
            f"Mandatory Skills: {must}\n\nGood to Have Skills: {nice}\n\n"
            f"Experience: {years}+ years\n\nQualification: B.E./B.Tech or equivalent")


def broken_jd(role, must, nice, years):
    style = random.choice(["free_text", "missing_some", "synonyms_ok"])
    if style == "free_text":
        return f"Need a {role} with {must}. {years} years exp. Immediate joiner preferred."
    if style == "missing_some":
        return (f"Role Summary: {role}\n\nResponsibilities:\n- Build and maintain systems\n\n"
                f"Skills: {must}")
    # synonyms that SHOULD still pass
    return (f"Job Summary: {role}\n\nRoles & Responsibilities:\n- Own delivery\n\n"
            f"Must Have Skills: {must}\n\nNice to Have: {nice}\n\n"
            f"Years of Experience: {years}\n\nEducation: Any graduate")


rows = []
for i in range(80):
    role, must, nice = random.choice(ROLES)
    years = random.randint(2, 12)
    status = random.choices(STATUSES, weights=[5, 3, 2])[0]
    jd = full_jd(role, must, nice, years) if random.random() < 0.55 else broken_jd(role, must, nice, years)
    rows.append({"demand_id": f"DM-{5000 + i}", "role": role, "demand_status": status, "jd_text": jd})

pd.DataFrame(rows).to_csv(OUT / "demands.csv", index=False)
print("wrote sample_data/demands.csv")

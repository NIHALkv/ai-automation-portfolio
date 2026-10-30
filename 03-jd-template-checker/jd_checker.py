"""
JD Template Checker

The downstream applicant-tracking system rejects job requests whose JD doesn't
contain the client's mandatory sections. This scores every JD, names what's
missing, and builds a compliance-by-status matrix.

    python jd_checker.py [--input demands.csv] [--out output/jd_check.xlsx]
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent

# Each required section, with the heading variants people actually write.
TEMPLATE: dict[str, list[str]] = {
    "Role Summary": ["role summary", "job summary", "position summary", "about the role"],
    "Responsibilities": ["key responsibilities", "roles? (?:&|and) responsibilities", "responsibilities"],
    "Mandatory Skills": ["mandatory skills", "must[- ]have skills", "primary skills", "required skills"],
    "Good to Have": ["good to have(?: skills)?", "nice to have(?: skills)?", "secondary skills"],
    "Experience": ["(?:years of )?experience", "exp(?:erience)? required"],
    "Qualification": ["qualifications?", "education"],
}


def heading_pattern(variants: list[str]) -> re.Pattern:
    # A heading = start of line, variant, then ':' or newline.
    return re.compile(r"(?im)^\s*(?:" + "|".join(variants) + r")\s*(?::|\n|$)")


PATTERNS = {name: heading_pattern(v) for name, v in TEMPLATE.items()}


def check_jd(text: str) -> tuple[bool, list[str], float]:
    text = text if isinstance(text, str) else ""
    missing = [name for name, pat in PATTERNS.items() if not pat.search(text)]
    score = 1 - len(missing) / len(PATTERNS)
    return not missing, missing, round(score, 2)


def run(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    res = df["jd_text"].apply(check_jd)
    df = df.assign(
        in_template=res.str[0],
        missing_sections=res.str[1].str.join(", "),
        template_score=res.str[2],
    )
    matrix = pd.crosstab(
        df["in_template"].map({True: "JD in template", False: "JD NOT in template"}),
        df["demand_status"], margins=True, margins_name="Total",
    )
    return df, matrix


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, default=HERE / "sample_data" / "demands.csv")
    ap.add_argument("--out", type=Path, default=HERE / "output" / "jd_check.xlsx")
    args = ap.parse_args()

    df = pd.read_csv(args.input) if args.input.suffix == ".csv" else pd.read_excel(args.input)
    detail, matrix = run(df)

    top_missing = (detail.loc[~detail.in_template, "missing_sections"].str.split(", ")
                   .explode().value_counts().rename_axis("section").reset_index(name="demands"))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(args.out) as xw:
        matrix.to_excel(xw, sheet_name="Matrix")
        top_missing.to_excel(xw, sheet_name="Most missed sections", index=False)
        detail.drop(columns="jd_text").to_excel(xw, sheet_name="Detail", index=False)

    print("Compliance matrix\n", matrix, "\n\nMost missed sections\n", top_missing.to_string(index=False), sep="")
    print(f"\nWritten to {args.out}")


if __name__ == "__main__":
    main()

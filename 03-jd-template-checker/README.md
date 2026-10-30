# 03 · JD Template Checker

Flags job descriptions that will break job-request creation, before they break it.

## Problem
The client's applicant-tracking system only accepted job requests whose JD followed a mandatory template. Recruiters wrote JDs freely, so creation failed with no clear reason. Nobody knew how many demands were affected or which sections were usually missing.

## What it does
1. Looks for 6 required sections in each JD: Role Summary, Responsibilities, Mandatory Skills, Good to Have, Experience, Qualification.
2. Accepts real-world **heading variants**, e.g. "Job Summary", "Must Have Skills", "Roles & Responsibilities", so good JDs aren't wrongly rejected.
3. Gives each JD a score and lists its missing sections.
4. Builds a **2×3 matrix**, in template vs not, by demand status (Migrated / Post go-live JR created / Internal). This tells the team where to focus.

## Run
```bash
python make_sample_data.py
python jd_checker.py            # matrix in terminal + output/jd_check.xlsx
```

## Design choice: rules first, then an LLM
Rules (regex over headings) are transparent, fast and easy for a business user to audit. They miss JDs where the content exists without a heading.

**Next step:** pass the failures to an LLM with the template and ask (a) which sections are really missing and (b) a rewritten JD in template format. Rules triage, the model fixes.

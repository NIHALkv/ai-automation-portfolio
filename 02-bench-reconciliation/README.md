# 02 · Bench Reconciliation

Finds every mismatch between three versions of the same truth: who is on bench and who is allocated.

## Problem
During a platform rollout, the client's bench count never matched ours. Data lived in three places: the client's HR export, our platform's allocations, and an offline bench sheet. Finding the gaps meant hours of VLOOKUPs, and nobody trusted the numbers.

## What it checks
| Gap | Meaning |
|-----|---------|
| Missing on platform | In client HR data, never loaded |
| Bench shown as billable | Platform says billable, client says bench |
| Wrong project | Allocated, but to a different project |
| Bench, not on bench sheet | Resourcing team doesn't know they're free |
| On bench sheet, but billable | Stale entry on the offline sheet |
| Users without allocation | Platform user with no allocation at all |

**Business rule encoded:** Boot Camp staff with WBS type `BN` are training, not bench, so they're excluded. Getting this wrong inflated bench numbers.

## Run
```bash
python make_sample_data.py        # synthetic data with planted gaps
python reconcile.py               # summary in terminal + output/bench_reconciliation.xlsx
python reconcile.py --data "C:/Users/me/Downloads"   # point at real exports
```
It always picks the **newest** file of each type, so teammates can re-download and re-run without renaming anything.

## Example output (synthetic data)
See the terminal summary after running. Every gap category is populated, because the generator plants known errors. That doubles as a test of the logic.

## Why it matters for AI
Any AI built on workforce data (staffing recommendations, demand forecasting) is only as good as the allocation data under it. This is the data-quality layer.

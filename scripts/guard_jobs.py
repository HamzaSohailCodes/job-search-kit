#!/usr/bin/env python3
"""Run posting_guard over many job descriptions at once (a run's jobs JSON or a tracker export).

Job posts are third-party text that Claude reads next to the candidate's personal data. This flags posts that carry
hidden text, invisible characters or lines written to an AI agent, so a human looks before Claude acts on them.

Usage:
  python3 scripts/guard_jobs.py --jobs <run>/kept.json [--field description] [--write-clean]
  python3 scripts/guard_jobs.py --tracker tracker/tracker.csv [--rows 40-120]

--jobs takes a JSON list (or {"jobs": [...]}) of dicts. The description field is auto-detected
(description, descriptionPlain, desc, content, job_description, "Job Description").
--write-clean replaces each description with the cleaned text (hidden blocks and invisible characters removed)
and writes <file>.clean.json next to the input; the original is never changed.
Exit code: 0 = no alarms, 1 = at least one post needs review, 2 = input error.
"""
import argparse, csv, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from posting_guard import guard  # noqa: E402

FIELDS = ["description", "descriptionPlain", "descriptionHtml", "desc", "content", "job_description", "Job Description"]
ALARM_KEYS = ("instruction_like", "invisible_text", "homoglyph_runs")


def alarmed(f):
    return bool(any(f.get(k) for k in ALARM_KEYS) or f.get("invisible_flagged") or (f.get("invisible_chars") or {}).get("tag"))


def pick_field(job, field):
    if field:
        return field if field in job else None
    return next((k for k in FIELDS if isinstance(job.get(k), str) and job.get(k)), None)


def label(job, i):
    co = job.get("company") or job.get("Company") or job.get("companyName") or ""
    ti = job.get("title") or job.get("Job Title") or job.get("role") or ""
    return f"#{i} {co} | {ti}".strip()


def check(items, field=None):
    """items: list of (label, dict). Returns (report rows, cleaned dicts)."""
    report, cleaned = [], []
    for lab, job in items:
        k = pick_field(job, field)
        if not k:
            cleaned.append(job); continue
        text, f = guard(job[k], "auto")
        if alarmed(f) or f.get("hidden_blocks"):
            report.append({"job": lab, "alarm": alarmed(f), "verdict": f["verdict"],
                           "instruction_like": f["instruction_like"][:5], "invisible_text": f["invisible_text"][:3],
                           "homoglyph_runs": f["homoglyph_runs"][:5], "hidden_blocks": f["hidden_blocks"][:3]})
        j = dict(job); j[k] = text; cleaned.append(j)
    return report, cleaned


def parse_rows(spec, n):
    if not spec:
        return None
    out = set()
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out.update(range(int(a), int(b or a) + 1))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--jobs"); g.add_argument("--tracker")
    ap.add_argument("--field"); ap.add_argument("--rows", help="sheet row numbers, e.g. 40-120 (row 2 = first data row)")
    ap.add_argument("--write-clean", action="store_true"); ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        if a.jobs:
            with open(a.jobs, encoding="utf-8") as f:
                data = json.load(f)
            wrapped = isinstance(data, dict)
            jobs = data.get("jobs", []) if wrapped else data
            items = [(label(j, i), j) for i, j in enumerate(jobs)]
        else:
            with open(a.tracker, encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))
            want = parse_rows(a.rows, len(rows))
            items = [(f"row {i + 2} {r.get('Company', '')} | {r.get('Job Title', '')}", r)
                     for i, r in enumerate(rows) if want is None or i + 2 in want]
            a.field = a.field or "Job Description"
    except (OSError, ValueError) as e:
        print(f"guard_jobs: cannot read input: {e}", file=sys.stderr); return 2
    report, cleaned = check(items, a.field)
    alarms = [r for r in report if r["alarm"]]
    if a.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"guard_jobs: {len(items)} posts checked, {len(alarms)} need review, "
              f"{len(report) - len(alarms)} had hidden blocks only (removed, not instruction-like)")
        for r in alarms:
            print(f"  ⚠ {r['job']}: {r['verdict']}")
            for line in r["instruction_like"] + r["invisible_text"]:
                print(f"      \"{line}\"")
    if a.write_clean and a.jobs:
        out = a.jobs.rsplit(".json", 1)[0] + ".clean.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump({**data, "jobs": cleaned} if wrapped else cleaned, f, ensure_ascii=False, indent=1)
        print(f"saved={out}")
    return 1 if alarms else 0


if __name__ == "__main__":
    sys.exit(main())

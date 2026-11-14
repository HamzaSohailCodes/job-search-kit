#!/usr/bin/env python3
"""Turn hand-picked candidates into tracker rows (columns A–AC, see scripts/tracker_header.md).

Usage: build_rows.py --run-dir DIR --date YYYY-MM-DD --picks picks.json

picks.json is a list of objects, one per chosen posting, in batch order:
  {"co": "acme", "title": "Senior Product Engineer",     # substrings matched against kept.json co/title
   "name": "Acme", "loc": "Austin, TX (Hybrid)", "pay": "$170K–$210K + equity",
   "score": 88, "resume": "<label from config/profile.json resumes[]>",
   "note": "fit sentence; gap: ...",
   "sponsor": "sponsorship not stated",                   # optional; default only when sponsorship matters
   "type": "Full-time"}      # optional: a column-L label or a config value (full_time, contract_c2c, ...);
                             # default: the type filter_jobs.py detected (kept.json emp_label), else "Not stated"

Columns: A title, B company, C location, D link, E pay, F 'Shortlisted', G applied date (blank),
H posted, I 'BATCH <date> #n | resume: <label> | fit; gap[; sponsor]', J score, K source,
L employment type, M blank, N job description, O blank (outcome), P blank (reason tag),
Q H-1B evidence (modules/h1b, only when modules.h1b is on; blank otherwise), R..AC blank (interview flag and the
contract/outreach columns that /search-contract-jobs fills). When L is "Not stated", I says why
("employment type not stated" or "contract; W2/C2C/1099 not stated").
Writes rows.json and rows.tsv in the run dir (29 columns, A..AC).
"""
import argparse, json, os, re, sys

_d = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(_d, "core", "config.py")) and _d != os.path.dirname(_d):
    _d = os.path.dirname(_d)
sys.path.insert(0, _d)
from core import config  # noqa: E402

SRC = {"Ashby": "Ashby — official company careers", "Greenhouse": "Greenhouse — official company careers",
       "Lever": "Lever — official company careers", "Workable": "Workable — official company careers",
       "LinkedIn": "LinkedIn", "Indeed": "Indeed", "YC": "YC Work at a Startup (ycombinator.com/jobs)"}
DESC_MAX = 30000  # a Sheets cell holds 50,000 characters
WIDTH = 29        # A..AC


def emp_label(value):
    """A pick's "type" (label or config value) -> the column-L label."""
    v = (value or "").strip()
    if v in config.EMPLOYMENT_TYPES:
        return config.employment_label(v)
    if v.lower() in config.LABEL_TO_TYPE:
        return config.EMPLOYMENT_TYPES[config.LABEL_TO_TYPE[v.lower()]]
    return "Not stated"


def clean(t):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t or "")).strip()[:DESC_MAX]


def h1b_cell_fn(p):
    """Returns company -> evidence text when modules.h1b is on, else a function returning ''."""
    if not config.module_on(p, "h1b"):
        return lambda name: ""
    sys.path.insert(0, config.path("modules", "h1b"))
    from h1b_lookup import lookup, evidence  # noqa: E402
    return lambda name: evidence(lookup(name))


def build(kept, picks, date, p, h1b=None):
    h1b = h1b or h1b_cell_fn(p)
    labels = {r.get("label") for r in config.get(p, "resumes", []) or []}
    needs = config.needs_sponsorship(p)

    def find(co, t):
        m = [o for o in kept if co.lower() in o["co"].lower() and t.lower() in o["title"].lower()]
        if len(m) != 1:
            raise SystemExit(f"pick ({co!r}, {t!r}) matched {len(m)} postings: {[o['title'] for o in m][:5]}")
        return m[0]

    rows = []
    for i, pk in enumerate(picks, 1):
        o = find(pk["co"], pk["title"])
        if labels and pk.get("resume") not in labels:
            print(f"WARNING: pick #{i} resume {pk.get('resume')!r} is not a label in profile resumes[] {sorted(labels)}", file=sys.stderr)
        sponsor = pk.get("sponsor", "sponsorship not stated" if needs else "")
        label = emp_label(pk["type"]) if pk.get("type") else (o.get("emp_label") or "Not stated")
        emp_note = (o.get("emp_note") or "employment type not stated") if label == "Not stated" else ""
        notes = (f"BATCH {date} #{i} | resume: {pk.get('resume', '')} | {pk['note']}" + (f"; {sponsor}" if sponsor else "")
                 + (f"; {emp_note}" if emp_note else ""))
        row = [o["title"].strip(), pk["name"], pk["loc"], o["url"], pk.get("pay") or o.get("comp") or "Not listed",
               "Shortlisted", "", o["date"], notes, str(pk["score"]), SRC.get(o["src"], o["src"]), label,
               "", clean(o.get("desc", "")), "", "", h1b(pk["name"])]
        rows.append(row + [""] * (WIDTH - len(row)))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build tracker rows from picks.json.")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--picks", required=True)
    a = ap.parse_args(argv)
    D = os.path.expanduser(a.run_dir)
    p = config.load()
    K = json.load(open(os.path.join(D, "kept.json")))
    P = json.load(open(os.path.expanduser(a.picks)))
    rows = build(K, P, a.date, p)
    json.dump(rows, open(os.path.join(D, "rows.json"), "w"))
    with open(os.path.join(D, "rows.tsv"), "w") as w:
        for r in rows:
            w.write("\t".join(c.replace("\t", " ").replace("\n", " ") for c in r) + "\n")
    for r in rows:
        print(r[9], "|", r[1], "|", r[0][:55], "|", r[3], ("| " + r[16]) if r[16] else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())

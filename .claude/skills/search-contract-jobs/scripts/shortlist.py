"""Turn a contract scraper CSV into today's shortlist, deduped against the one tracker tab.

Drops roles already in the tracker export (every row and every work type: a role already there as
full-time is a duplicate; matched by link, or by title + company), drops companies contacted today
(tracker column "Contacted On" = today, plus --contacted), and keeps one role per company (highest score).

Usage (repo root):
  python3 .claude/skills/search-contract-jobs/scripts/shortlist.py \
      --jobs batches/<date>-c2c/c2c_jobs_<date>.csv [--tracker tracker/tracker.csv] \
      [--contacted "Company A;Company B"] [--min-score 70] [--out batches/<date>-c2c/shortlist.csv] \
      [--rows-out batches/<date>-c2c/tracker_rows.tsv] [--first-row N]

--tracker is a full CSV/TSV export of the tracker tab (headers as in scripts/tracker_header.md; Job Title,
Company and Job Link are read by name, else by position A, B, D).
--rows-out also writes the shortlist as tracker rows A..AC (29 columns, email drafts left blank), to paste
below the last row, plus the same rows as JSON (<rows-out>.json) for .claude/skills/search-jobs/scripts/check_dupes.py. --first-row (for the follow-up formulas) defaults to the row after the export's last row.
--min-score defaults to c2c.shortlist_min_score in config/profile.json (70).
"""
import argparse
import csv
import json
import os
import re
import sys
from datetime import date, datetime

DEFAULT_MIN = 70
csv.field_size_limit(10**8)


def _root():
    d = os.path.dirname(os.path.abspath(__file__))
    while not os.path.exists(os.path.join(d, "core", "config.py")) and d != os.path.dirname(d):
        d = os.path.dirname(d)
    return d


ROOT = _root()
sys.path.insert(0, ROOT)


def norm(s):
    s = re.sub(r"\b(inc|llc|corp|corporation|ltd|technologies|technology|solutions|group|co)\b\.?", "", (s or "").lower())
    return re.sub(r"[^a-z0-9]", "", s)


def url_key(u):
    """Same posting across URL forms: Dice job UUID, LinkedIn/ATS numeric id, else the URL without query."""
    u = (u or "").strip().lower()
    m = (re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", u)
         or re.search(r"(?:currentjobid|gh_jid|jk)=([0-9a-z]+)", u) or re.search(r"(\d{8,})", u.split("?")[0]))
    return m.group(1) if m else u.split("?")[0].split("#")[0].rstrip("/")


def read(path):
    with open(path, newline="") as f:
        head = f.readline()
        f.seek(0)
        return list(csv.DictReader(f, delimiter="\t" if "\t" in head else ","))


def tracker_entries(rows):
    """[(title, company, link, contacted_on)] from tracker export dicts (by header, else position A, B, D, AA)."""
    out = []
    for r in rows:
        vals = list(r.values())
        pick = lambda name, i: r.get(name) if name in r else (vals[i] if len(vals) > i else "")  # noqa: E731
        out.append((pick("Job Title", 0) or "", pick("Company", 1) or "", pick("Job Link", 3) or "",
                    pick("Contacted On", 26) or ""))
    return out


def _is_today(s, today):
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(s, fmt).date() == today
        except ValueError:
            continue
    return False


def _score(r):
    try:
        return int(float(r.get("Score") or 0))
    except ValueError:
        return 0


def shortlist(jobs, tracker, contacted=(), min_score=0, today=None):
    """jobs: scraper CSV dicts; tracker: tracker export dicts. Returns (rows best first, dropped counts)."""
    today = today or date.today()
    entries = tracker_entries(tracker)
    seen_links = {url_key(link) for _, _, link, _ in entries if link}
    seen_roles = {(norm(t), norm(c)) for t, c, _, _ in entries if t}
    contacted_today = {norm(c) for c in contacted if c and c.strip()}
    contacted_today |= {norm(c) for _, c, _, on in entries if c and _is_today(on, today)}

    best = {}
    dropped = {"already in tracker": 0, "company contacted today": 0, "below min score": 0,
               "second role at same company": 0}
    for r in jobs:
        s = _score(r)
        if url_key(r.get("Link")) in seen_links or (norm(r.get("Title")), norm(r.get("Company"))) in seen_roles:
            dropped["already in tracker"] += 1
            continue
        c = norm(r.get("Company"))
        if c in contacted_today:
            dropped["company contacted today"] += 1
            continue
        if s < min_score:
            dropped["below min score"] += 1
            continue
        if c in best:
            dropped["second role at same company"] += 1
            if s <= _score(best[c]):
                continue
        best[c] = r
    return sorted(best.values(), key=lambda r: -_score(r)), dropped


def _profile():
    from core import config
    return config, config.load(required=False)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", required=True)
    ap.add_argument("--tracker", default=os.path.join(ROOT, "tracker", "tracker.csv"))
    ap.add_argument("--contacted", default="", help="extra companies contacted today, separated by ;")
    ap.add_argument("--min-score", type=int)
    ap.add_argument("--out")
    ap.add_argument("--rows-out", help="also write tracker rows A..AC (TSV) here")
    ap.add_argument("--first-row", type=int, help="sheet row of the first new row (default: after the export)")
    ap.add_argument("--raw", help="raw_jobs JSON for column N (default: newest next to --jobs)")
    a = ap.parse_args(argv)

    config, p = _profile()
    if p and not config.module_on(p, "c2c"):
        sys.exit("The contract search is off: no contract work type is selected. Add a contract type with "
                 "/setup → update my profile (targets.employment_types).")
    min_score = a.min_score if a.min_score is not None else int(config.get(p, "c2c.shortlist_min_score", DEFAULT_MIN)
                                                                 or DEFAULT_MIN)
    if os.path.exists(a.tracker):
        tracker = read(a.tracker)
    else:
        print(f"Warning: no tracker export at {a.tracker}; nothing to dedupe against. Export the tracker first.",
              file=sys.stderr)
        tracker = []

    rows, dropped = shortlist(read(a.jobs), tracker, a.contacted.split(";"), min_score)
    out = open(a.out, "w", newline="") if a.out else sys.stdout
    try:
        if rows:
            w = csv.DictWriter(out, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    finally:
        if a.out:
            out.close()
    if a.rows_out:
        sys.path.insert(0, os.path.join(ROOT, "modules", "c2c", "outreach"))
        import build_outreach as bo
        first = a.first_row or len(tracker) + 2
        descs = bo.be.load_descriptions(a.jobs, a.raw)
        trows = bo.build_rows(p, rows, descs, {}, first, drafts=False)
        bo.write_tsv(a.rows_out, trows)
        rows_json = os.path.splitext(a.rows_out)[0] + ".json"
        with open(rows_json, "w") as f:
            json.dump(trows, f)
        print(f"tracker rows A..AC -> {a.rows_out} and {rows_json} (first row {first})", file=sys.stderr)
    print(f"kept {len(rows)}; dropped: " + (", ".join(f"{k} {v}" for k, v in dropped.items() if v) or "none"),
          file=sys.stderr)


if __name__ == "__main__":
    main()

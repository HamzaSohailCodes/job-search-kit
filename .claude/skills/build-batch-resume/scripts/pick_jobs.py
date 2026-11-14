#!/usr/bin/env python3
"""Pick the jobs to tailor resumes for, from the tracker export (tracker/tracker.csv by default).

Rules: Apply Status = Shortlisted, Match Score >= --min-score, posted within --days (rows with "~" dates are
approximate and count only with --allow-approx), job description >= 1,500 chars, one role per company, never a
company already Applied / Rejected / Interviewing / Skipped / Offer, and skip companies that already have a
tailored folder under resumes/tailored/. Postings that match the profile's domain skips (targets.domain_skips) are
dropped; when the candidate needs sponsorship, postings that say they don't sponsor are dropped too.
Order: with modules.h1b on, H-1B evidence first (sponsors > some > other > no); then score, then newest.

Defaults for --n / --days / --min-score come from config resume_build.batch_size / batch_days / min_score.

Usage (repo root): python3 .claude/skills/build-batch-resume/scripts/pick_jobs.py --out jobs.json [--tracker CSV]
"""
import argparse
import csv
import datetime as dt
import glob
import json
import os
import re
import sys

_d = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(_d, "core", "config.py")) and _d != os.path.dirname(_d):
    _d = os.path.dirname(_d)
sys.path.insert(0, _d)
from core import config  # noqa: E402

DONE = {"Applied", "Rejected", "Interviewing", "Skipped", "Offer"}

# Postings that rule out visa sponsorship (used only when the candidate needs it).
SPONSOR_BLOCK = re.compile(
    r"(not|unable to|cannot|can ?not|won't|will not|do not|does not|no)\s+(currently\s+)?(offer|provide|sponsor|support)\w*\s+"
    r"(\w+\s+){0,4}(visa|sponsorship|h-?1b|immigration)|"
    r"without (the need for |requiring |need of )?(current or future |future |any )?(visa )?sponsorship|"
    r"no (visa )?sponsorship|sponsorship (is )?not (available|offered|provided)|"
    r"u\.?s\.? citizen(s|ship)? (only|is required|required)|must be a u\.?s\.? citizen|green card holders? only|"
    r"not (eligible|able) to sponsor|unable to sponsor|will not sponsor|does not sponsor|cannot sponsor|"
    r"does not provide immigration support", re.I)


def norm(c):
    c = re.sub(r"[^a-z0-9 ]", " ", (c or "").lower())
    c = re.sub(r"\b(inc|llc|ltd|corp|corporation|co|ai|labs?|technologies|technology|hq|the)\b", " ", c)
    return " ".join(c.split())


def slug(s):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", (s or "").lower())).strip("-")[:60]


def h1b_rank(q):
    q = (q or "").lower()
    return 0 if q.startswith("sponsors") else 1 if q.startswith("some") else 3 if q.startswith("no") else 2


def pick(rows, p, n=50, days=21, min_score=70, allow_approx=False, today=None, tailored=None):
    """Return (picks, drops) from tracker rows (dicts keyed by the tracker's column names)."""
    g = lambda r, k: (r.get(k) or "").strip()  # noqa: E731
    today = dt.date.fromisoformat(today) if today else dt.date.today()
    blocked = {norm(g(r, "Company")) for r in rows if g(r, "Apply Status") in DONE}
    tailored = tailored if tailored is not None else {
        os.path.basename(x) for x in glob.glob(config.path("resumes", "tailored", "*", "*")) if os.path.isdir(x)}
    cutoff = today - dt.timedelta(days=days)
    skips = [(re.compile(s["regex"], re.I), s.get("label", "domain skip")) for s in config.get(p, "targets.domain_skips", [])
             if s.get("regex")]
    needs_visa = config.needs_sponsorship(p)
    use_h1b = config.module_on(p, "h1b")

    drops, cands = {}, []

    def drop(why):
        drops[why] = drops.get(why, 0) + 1
    for r in rows:
        if g(r, "Apply Status") != "Shortlisted":
            continue
        sc = int(g(r, "Match Score")) if g(r, "Match Score").isdigit() else 0
        if sc < min_score:
            drop("score"); continue
        posted = g(r, "Job Posted At")
        if posted.startswith("~") and not allow_approx:
            drop("approx date"); continue
        try:
            d = dt.date.fromisoformat(posted.lstrip("~")[:10])
        except ValueError:
            drop("no date"); continue
        if d < cutoff:
            drop("old"); continue
        desc = g(r, "Job Description")
        if needs_visa and SPONSOR_BLOCK.search(desc):
            drop("posting blocks sponsorship"); continue
        hit = next((lab for rx, lab in skips if rx.search(desc)), None)
        if hit:
            drop(f"domain skip: {hit}"); continue
        if len(desc) < 1500:
            drop("thin description"); continue
        if norm(g(r, "Company")) in blocked:
            drop("company already applied/skipped"); continue
        cs = slug(g(r, "Company"))
        if any(t == cs or t.startswith(cs + "-") for t in tailored):
            drop("already tailored"); continue
        r["_score"], r["_date"] = sc, d
        cands.append(r)

    cands.sort(key=lambda r: ((h1b_rank(g(r, "H-1B Evidence")) if use_h1b else 0), -r["_score"], -r["_date"].toordinal()))
    seen, picks = set(), []
    for r in cands:
        k = norm(g(r, "Company"))
        if k in seen:
            drop("second role at company"); continue
        seen.add(k)
        picks.append(r)
        if len(picks) >= n:
            break
    jobs = [{"key": slug(g(r, "Company") + " " + g(r, "Job Title")), "company": g(r, "Company"), "title": g(r, "Job Title"),
             "url": g(r, "Job Link"), "row": r.get("_row"), "score": r["_score"], "posted": g(r, "Job Posted At"),
             "location": g(r, "Location"), "pay": g(r, "Pay Scale"),
             "h1b": g(r, "H-1B Evidence")[:80] if use_h1b else "", "desc": g(r, "Job Description")} for r in picks]
    return jobs, drops


def main():
    p = config.load()
    ap = argparse.ArgumentParser()
    ap.add_argument("--tracker", default=config.path("tracker", "tracker.csv"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, default=int(config.get(p, "resume_build.batch_size", 50)))
    ap.add_argument("--days", type=int, default=int(config.get(p, "resume_build.batch_days", 21)))
    ap.add_argument("--min-score", type=int, default=int(config.get(p, "resume_build.min_score", 70)))
    ap.add_argument("--allow-approx", action="store_true")
    ap.add_argument("--today", default=dt.date.today().isoformat())
    a = ap.parse_args()
    if not config.module_on(p, "resume_tailoring"):
        sys.exit("modules.resume_tailoring is off in config/profile.json; turn it on to tailor resumes.")
    if not os.path.exists(a.tracker):
        sys.exit(f"No tracker export at {a.tracker}. Export the tracker sheet to tracker/tracker.csv first.")
    with open(a.tracker, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for i, r in enumerate(rows):
        r["_row"] = i + 2
    jobs, drops = pick(rows, p, a.n, a.days, a.min_score, a.allow_approx, a.today)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=1, ensure_ascii=False)
    print(f"picked {len(jobs)}; dropped: {drops}")
    for j in jobs:
        print(f"{j['row']:>4} {j['score']:>3} {j['posted'][:10]} {j['h1b'][:12]:<12} {j['company'][:24]:<24} {j['title'][:60]}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Which applications get replies? Response rates by segment, to tune how jobs are picked and scored.

Counts every submitted application in tracker/tracker.csv (status Applied, Rejected, Interviewing, Offer, or a
contract row with Contacted On (AA) set) and
classifies it from the status plus applications/_events.jsonl:
  positive = Interviewing / Offer status, Reached Interview (R) = Yes, a contract outreach stage in O of
             Replied / Screen call / Submitted (RTR) / Client interview, or an interview, assessment or offer event
  rejected = Rejected status or a rejected event (and no positive signal)
  silent   = everything else
Segments: employment type (L: Full-time, Part-time, Contract (W2/C2C/1099), Not stated), source (K), match score band (J), role type (from the title), resume (from Notes "resume: <label>"),
the week applied, and the H-1B tier (column Q) when modules.h1b is on. Rejection reason tags (P) are counted
separately.

The report suggests; it changes nothing. Rubric or filter changes go to the candidate first, then into
the search/apply skills and soul.md.

Role types: calibration.role_types in config/profile.json ([[name, regex], ...]) or the generic list below.

Usage: python3 scripts/calibrate.py [--min-n 5] [--write] [--tracker tracker/tracker.csv]
       (--write saves reviews/<today>-calibration.md)
Data location: the repo root, or $JOB_KIT_DATA if set.
"""
import argparse, collections, datetime as dt, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_applications import (REPLIED_STAGES, company_key, data_root, dpath, employment_segment,  # noqa: E402
                                load_events, outreach_stage, profile, read_csv, role_events, write_text)
from followups import parse_date  # noqa: E402
from core import config  # noqa: E402

SUBMITTED = ("Applied", "Rejected", "Interviewing", "Offer")
ROLE_TYPES = [("forward deployed / solutions", r"forward[- ]deployed|\bFDE\b|deployment engineer|solutions engineer"),
              ("founding", r"founding"), ("product engineer", r"product engineer"),
              ("AI / ML", r"\bAI\b|\bLLM\b|machine learning|\bML\b|agent"),
              ("full-stack", r"full[- ]?stack"), ("frontend", r"front[- ]?end|\bUI\b"),
              ("backend / platform", r"back[- ]?end|platform|infra|data|distributed")]


def role_types(p=None):
    custom = config.get(p if p is not None else profile(), "calibration.role_types", None)
    if custom:
        return [(str(n), str(rx)) for n, rx in custom]
    return ROLE_TYPES


def h1b_tier(q):
    q = (q or "").lower()
    for t in ("sponsors", "some", "none", "ambiguous"):
        if q.startswith(t) or (t == "none" and "no lca" in q) or (t == "ambiguous" and "ambiguous" in q):
            return t
    return "unknown"


def source_of(k):
    k = (k or "").lower()
    for name in ("ashby", "greenhouse", "lever", "linkedin", "yc", "work at a startup", "indeed", "glassdoor",
                 "wellfound", "dice", "referral", "email"):
        if name in k:
            return "YC" if name in ("yc", "work at a startup") else name.title()
    return "other" if k else "unknown"


def band(j):
    try:
        v = float(j)
    except (TypeError, ValueError):
        return "no score"
    return "90+" if v >= 90 else f"{int(v // 10) * 10}s" if v >= 60 else "under 60"


def role_type(title, types=None):
    for name, rx in (types or ROLE_TYPES):
        if re.search(rx, title or "", re.I):
            return name
    return "other"


def resume_of(notes):
    m = re.search(r"resume:\s*([A-Za-z0-9_ ()/.-]+?)(?:\s*\||,|;|$)", notes or "", re.I)
    if not m:
        return "not recorded"
    r = m.group(1).strip()
    return "tailored" if r.lower().startswith("tailored") else r[:20]


def outcome(row, evs):
    st = (row.get("Apply Status") or "").strip()
    kinds = {e.get("event") for e in evs}
    if (st in ("Interviewing", "Offer") or kinds & {"interview", "assessment", "offer"}
            or (row.get("Reached Interview") or "").strip().lower() == "yes"
            or outreach_stage(row.get("Outcome / Next Step")) in REPLIED_STAGES):
        return "positive"
    if st == "Rejected" or "rejected" in kinds:
        return "rejected"
    return "silent"


def analyse(rows, events, types=None):
    apps = []
    for r in rows:
        contacted = (r.get("Contacted On") or "").strip()  # contract outreach counts as an application
        if (r.get("Apply Status") or "").strip() not in SUBMITTED and not contacted:
            continue
        evs = role_events(events.get(company_key(r.get("Company", "")), []), r.get("Job Title", ""))
        d = parse_date(r.get("Applied Date")) or parse_date(contacted) or next((parse_date(e.get("date")) for e in evs if e.get("event") == "submitted"), None)
        apps.append({"outcome": outcome(r, evs), "reason": (r.get("Reason Tag") or "").strip() or "untagged",
                     "H-1B tier": h1b_tier(r.get("H-1B Evidence")), "source": source_of(r.get("Source")),
                     "employment type": employment_segment(r.get("Employment Type")),
                     "score band": band(r.get("Match Score")), "role type": role_type(r.get("Job Title"), types),
                     "resume": resume_of(r.get("Notes")),
                     "week applied": (d - dt.timedelta(days=d.weekday())).isoformat() if d else "undated"})
    return apps


def table(apps, key, min_n, overall):
    g = collections.defaultdict(collections.Counter)
    for a in apps:
        g[a[key]][a["outcome"]] += 1
    lines = [f"### By {key}", "", "| Segment | Applied | Positive | Rate | Rejected | Silent | Signal |", "|---|---|---|---|---|---|---|"]
    for seg, c in sorted(g.items(), key=lambda kv: -sum(kv[1].values())):
        n = sum(c.values()); rate = c["positive"] / n if n else 0
        sig = ""
        if n >= min_n and overall:
            # "below" needs enough volume that at least 2 positives were expected at the overall rate
            sig = ("above average" if rate >= overall * 1.5 and c["positive"] >= 2
                   else "below average" if rate <= overall * 0.5 and n * overall >= 2 else "")
        elif n < min_n:
            sig = "too few"
        lines.append(f"| {seg} | {n} | {c['positive']} | {rate:.0%} | {c['rejected']} | {c['silent']} | {sig} |")
    return lines + [""]


def segment_keys(h1b=False):
    keys = ["employment type", "source", "score band", "role type", "resume", "week applied"]
    return (["H-1B tier"] + keys) if h1b else keys


def report(apps, min_n=5, today=None, h1b=None):
    if h1b is None:
        h1b = config.module_on(profile(), "h1b")
    n = len(apps)
    pos = sum(a["outcome"] == "positive" for a in apps)
    overall = pos / n if n else 0
    out = [f"# Calibration {today or dt.date.today().isoformat()}", "",
           f"{n} submitted applications, {pos} positive ({overall:.0%}), "
           f"{sum(a['outcome'] == 'rejected' for a in apps)} rejected, {sum(a['outcome'] == 'silent' for a in apps)} silent.",
           f"Signal = a segment with {min_n}+ applications whose positive rate is at least 1.5x (and 2+ positives) or at most half the overall rate (with 2+ positives expected).", ""]
    for key in segment_keys(h1b):
        out += table(apps, key, min_n, overall)
    rej = collections.Counter(a["reason"] for a in apps if a["outcome"] == "rejected")
    out += ["### Rejection reasons (column P)", ""] + [f"- {k}: {v}" for k, v in rej.most_common()] + [""]
    out += ["### What to do with this", "",
            "- Segments marked above average: pick more from them (raise their weight in the shortlist rubric or pick order).",
            "- Segments marked below average: ask the candidate before lowering them; small samples mislead.",
            "- If score bands don't separate positives from silence, the rubric isn't predicting replies; review the weights.", ""]
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Reply rates by segment from the tracker export and events.")
    ap.add_argument("--tracker", default=None, help="tracker export (default tracker/tracker.csv in the data root)")
    ap.add_argument("--min-n", type=int, default=5); ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    path = a.tracker or dpath("tracker", "tracker.csv")
    if not os.path.exists(path):
        print(f"no tracker export at {path}; export the tracker tab to CSV first", file=sys.stderr)
        return 2
    apps = analyse(read_csv(path, dict_rows=True), load_events(), role_types())
    text = report(apps, a.min_n)
    if a.write:
        p = dpath("reviews", f"{dt.date.today().isoformat()}-calibration.md")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        write_text(p, text + "\n"); print(os.path.relpath(p, data_root()))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Find remote C2C jobs from Dice, LinkedIn and staffing-firm career sites, filter, score, write a CSV.

Settings come from config/profile.json (see settings.py). Run from the repo root:

  python3 modules/c2c/scraper/run.py --check-config     # show the effective settings and queries, no network
  python3 modules/c2c/scraper/run.py                    # everything, window = c2c.days
  python3 modules/c2c/scraper/run.py --only dice --days 1
  python3 modules/c2c/scraper/run.py --only linkedin
  python3 modules/c2c/scraper/run.py --rescore batches/<date>-c2c/raw_jobs_<date>.json

Output goes to batches/<today>-c2c/: c2c_jobs_<date>.csv (score >= min, best first; Employment Type is the
tracker label for column L, "Not stated" when the post is unclear) and raw_jobs_<date>.json (everything
fetched, for --rescore).
Exit code 3 when no contract type is picked (targets.employment_types in config/profile.json).
"""
import argparse
import collections
import csv
import dataclasses
import json
import os
import re
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import filters  # noqa: E402
import settings as c2c_settings  # noqa: E402
from settings import config  # noqa: E402


# Scraper output. shortlist.py turns it into tracker rows (A..AC, scripts/tracker_header.md).
CSV_HEADER = ["Score", "C2C", "Employment Type", "Rate / Terms", "Title", "Company", "Location", "Tier", "Source",
              "Posted", "Pay", "Years asked", "Skills matched", "Link"]


def location(j):
    if j.remote:
        return "Remote (US)"
    return j.location or ""


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def title_ok(prof, t):
    t = f" {t.lower()} "
    return any(x in t for x in prof["title_include"]) and not any(x in t for x in prof["title_exclude"])


def print_settings(prof, log):
    log("C2C settings (from config/profile.json):")
    log(f"  contract_types: {', '.join(prof['contract_types']) or '(none)'}")
    log(f"  hourly_floor: {prof['hourly_floor'] or 'none'}")
    for k in ("years", "level", "needs_sponsorship", "us_citizen", "days", "remote_only", "max_years_asked",
              "min_score", "skip_clearance"):
        log(f"  {k}: {prof[k]}")
    log(f"  skills.core: {', '.join(prof['skills']['core']) or '(empty: set targets.skills.core)'}")
    log(f"  skills.ai: {', '.join(prof['skills']['ai']) or '(none)'}")
    log(f"  title_include: {len(prof['title_include'])} terms; title_exclude: {len(prof['title_exclude'])} terms")
    for k, v in prof["queries"].items():
        tag = " (generated)" if k in prof["queries_generated"] else ""
        log(f"  queries.{k}{tag}: {'; '.join(v)}")
    fb = prof["firm_boards"]
    log(f"  firm boards: {fb if os.path.exists(fb) else 'none (' + fb + ' missing; firm sites are skipped)'}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["dice", "linkedin", "firms"])
    ap.add_argument("--days", type=int)
    ap.add_argument("--dice-pages", type=int, default=5)
    ap.add_argument("--min-score", type=int, help="default: c2c.min_score (55)")
    ap.add_argument("--out", help="default: batches/<today>-c2c/")
    ap.add_argument("--rescore", metavar="RAW_JSON", help="skip searching; rescore jobs saved by an earlier run")
    ap.add_argument("--check-config", action="store_true", help="print the effective settings and exit")
    args = ap.parse_args(argv)
    log = lambda m: print(m, file=sys.stderr, flush=True)  # noqa: E731

    prof = c2c_settings.load_settings()
    if not prof["enabled"]:
        log(c2c_settings.MODULE_OFF)
        return 3
    if args.days:
        prof["days"] = args.days
    min_score = prof["min_score"] if args.min_score is None else args.min_score
    if args.check_config:
        print_settings(prof, log)
        return 0
    if not prof["skills"]["core"]:
        log("Warning: targets.skills.core is empty in config/profile.json, so every role scores low on skills.")

    today = date.today().isoformat()
    out_dir = args.out or config.path("batches", f"{today}-c2c")

    jobs = []
    if args.rescore:
        from common import Job
        with open(args.rescore) as f:
            jobs = [Job(**d) for d in json.load(f)]
        args.only = "none"
    if args.only in (None, "dice"):
        import source_dice
        log("Dice (remote; Third Party jobs + contract jobs matching the keyword queries):")
        emp = "THIRD_PARTY" if "contract_c2c" in prof["contract_types"] else "CONTRACTS"
        jobs += source_dice.collect(prof["queries"]["dice"], args.dice_pages, prof["days"], log,
                                    keyword_queries=prof["queries"].get("dice_keyword", []), emp=emp)
    if args.only in (None, "linkedin"):
        import source_linkedin
        log("LinkedIn (remote, contract):")
        jobs += source_linkedin.collect(prof["queries"]["linkedin"], prof["days"],
                                        lambda t: title_ok(prof, t), log)
    if args.only in (None, "firms"):
        if os.path.exists(prof["firm_boards"]):
            import source_firms
            log("Staffing-firm sites:")
            jobs += source_firms.collect(prof["firm_boards"], log)
        else:
            log(f"Staffing-firm sites: skipped ({prof['firm_boards']} not found; "
                "copy firm_boards.example.json to firm_boards.json to use them)")

    # Dedupe on title + company (the same role is often posted in several places).
    uniq = {}
    for j in jobs:
        uniq.setdefault((norm(j.title), norm(j.company)), j)
    jobs = list(uniq.values())

    os.makedirs(out_dir, exist_ok=True)
    if not args.rescore:
        raw = os.path.join(out_dir, f"raw_jobs_{today}.json")
        with open(raw, "w") as f:
            json.dump([dataclasses.asdict(j) for j in jobs], f)
        log(f"Saved all fetched jobs to {raw} (rescore later with --rescore)")

    kept, dropped = [], collections.Counter()
    for j in jobs:
        ok, why = filters.check(j, prof)
        if not ok:
            dropped[why] += 1
            continue
        s, info = filters.score(j, prof)
        if s < min_score:
            dropped["score below minimum"] += 1
            continue
        kept.append((s, j, info))
    kept.sort(key=lambda r: (-r[0], r[1].posted))

    path = os.path.join(out_dir, f"c2c_jobs_{today}.csv")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(CSV_HEADER)
        for s, j, info in kept:
            w.writerow([s, info["c2c"], config.employment_label(info["employment_type"]), info["terms"], j.title,
                        j.company, location(j), j.tier, j.source, j.posted, j.pay, info["years_asked"],
                        info["skills_hit"], j.url])

    log(f"\nCollected {len(jobs)} unique jobs, kept {len(kept)}, dropped {sum(dropped.values())}:")
    for why, n in dropped.most_common():
        log(f"  {n:4d}  {why}")
    log(f"\nWrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

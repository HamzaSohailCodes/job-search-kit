#!/usr/bin/env python3
"""Find applications that need a nudge, a thank-you, or closing as no response.

Reads tracker/tracker.csv (export of the tracker tab) and applications/_events.jsonl. Writes nothing; the
follow-ups skill drafts notes from this list and the candidate sends them.

Buckets (defaults come from followups.* in config/profile.json)
  followup   Applied, no reply event, quiet for >= --days (followups.quiet_days, 10) since the last touch,
             fewer than followups.max_followups (2) follow-ups sent
  thankyou   an interview event in the last followups.thankyou_days (3) with no follow-up logged after it
  checkin    Interviewing, last event more than followups.checkin_days (7) ago
  stale      Applied, no reply event, >= --stale days (followups.stale_days, 60) since applying:
             propose Outcome "No response"
  undated    Applied with no applied date and no submitted event (fix the date first)

Contract rows (column L is Contract (W2/C2C/1099)) that the candidate has contacted (AA Contacted On set) use
the outreach dates instead of quiet_days: follow-up 1 is due on AB (or AA + c2c.followup_workdays[0] workdays,
default 3), follow-up 2 on AC (or AA + [1], default 5); two follow-ups at most. They count as replied once O
starts with Replied / Screen call / Submitted (RTR) / Client interview or a reply event is logged. Contract rows
with F = Shortlisted are included once contacted. Contract items carry contract=true, due, contacted.

Usage:
  python3 scripts/followups.py [--days 10] [--stale 60] [--company acme] [--today YYYY-MM-DD] [--json]
                               [--tracker tracker/tracker.csv]
Data location: the repo root, or $JOB_KIT_DATA if set.
"""
import argparse, datetime as dt, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_applications import (REPLIED_STAGES, company_key, contract_followup_dates, dpath, is_contract,  # noqa: E402
                                load_events, outreach_stage, profile, read_csv, role_events)
from core import config  # noqa: E402  (path set up by build_applications)

REPLY = ("interview", "assessment", "offer", "rejected", "withdrawn", "no_response")


def settings(p=None):
    p = p if p is not None else profile()
    g = lambda k, d: int(config.get(p, "followups." + k, d) or d)  # noqa: E731
    return {"days": g("quiet_days", 10), "stale": g("stale_days", 60), "max_followups": g("max_followups", 2),
            "thankyou_days": g("thankyou_days", 3), "checkin_days": g("checkin_days", 7)}


MAX_FOLLOWUPS = settings({})["max_followups"]


def parse_date(s):
    s = (s or "").strip().lstrip("~")
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(s[:10] if fmt == "%Y-%m-%d" else s, fmt).date()
        except ValueError:
            continue
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    try:
        return dt.date.fromisoformat(m.group(1)) if m else None
    except ValueError:
        return None


def classify(rows, events, today, days=10, stale=60, company=None, max_followups=None,
             thankyou_days=3, checkin_days=7, p=None):
    max_followups = MAX_FOLLOWUPS if max_followups is None else max_followups
    out = {k: [] for k in ("followup", "thankyou", "checkin", "stale", "undated")}
    for i, r in enumerate(rows):
        status = (r.get("Apply Status") or "").strip()
        contract = is_contract(r.get("Employment Type", ""))
        contacted = parse_date(r.get("Contacted On")) if contract else None
        if status not in ("Applied", "Interviewing") and not (contacted and status == "Shortlisted"):
            continue
        co, title = r.get("Company", ""), r.get("Job Title", "")
        if company and company.lower() not in co.lower():
            continue
        evs = role_events(events.get(company_key(co), []), title)
        dated = [(parse_date(e.get("date")), e) for e in evs]
        dated = [(d, e) for d, e in dated if d]
        applied = parse_date(r.get("Applied Date")) or next((d for d, e in dated if e.get("event") == "submitted"), None)
        fups = [d for d, e in dated if e.get("event") == "followup"]
        replies = [(d, e) for d, e in dated if e.get("event") in REPLY]
        last_touch = max([d for d, e in dated if e.get("event") not in ("shortlisted", "filled")] + ([applied] if applied else []), default=None)
        item = {"row": i + 2, "company": co, "title": title, "status": status, "link": r.get("Job Link", ""),
                "applied": applied.isoformat() if applied else "", "last_touch": last_touch.isoformat() if last_touch else "",
                "days_quiet": (today - last_touch).days if last_touch else None, "followups_sent": len(fups),
                "outcome": (r.get("Outcome / Next Step") or "")[:160], "h1b": (r.get("H-1B Evidence") or "")[:40],
                "type": (r.get("Employment Type") or "").strip()}
        ints = [d for d, e in dated if e.get("event") == "interview"]
        if ints and (today - max(ints)).days <= thankyou_days and not any(d >= max(ints) for d in fups):
            out["thankyou"].append(item)
        if status == "Interviewing":
            if last_touch and (today - last_touch).days > checkin_days:
                out["checkin"].append(item)
            continue
        if replies:
            continue
        if contacted:
            if outreach_stage(r.get("Outcome / Next Step")) in REPLIED_STAGES:
                continue
            f1, f2 = contract_followup_dates(r.get("Contacted On"), r.get("Follow-up 1"), r.get("Follow-up 2"), p, parse_date)
            sent = len([d for d in fups if d >= contacted])
            due = f1 if sent == 0 else f2 if sent == 1 else None
            item.update(contract=True, contacted=contacted.isoformat(), due=due.isoformat() if due else "",
                        days_quiet=(today - max([contacted] + fups)).days, followups_sent=sent)
            if (today - contacted).days >= stale:
                out["stale"].append(item)
            elif due and today >= due:
                out["followup"].append(item)
            continue
        if not applied:
            out["undated"].append(item); continue
        if (today - applied).days >= stale:
            out["stale"].append(item)
        elif item["days_quiet"] is not None and item["days_quiet"] >= days and len(fups) < max_followups:
            out["followup"].append(item)
    for k in out:
        out[k].sort(key=lambda x: -(x["days_quiet"] or 0))
    return out


def main(argv=None):
    s = settings()
    ap = argparse.ArgumentParser(description="List applications due a follow-up, thank-you, check-in or closing.")
    ap.add_argument("--tracker", default=None, help="tracker export (default tracker/tracker.csv in the data root)")
    ap.add_argument("--days", type=int, default=s["days"]); ap.add_argument("--stale", type=int, default=s["stale"])
    ap.add_argument("--company"); ap.add_argument("--today"); ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    today = dt.date.fromisoformat(a.today) if a.today else dt.date.today()
    path = a.tracker or dpath("tracker", "tracker.csv")
    if not os.path.exists(path):
        print(f"no tracker export at {path}; export the tracker tab to CSV first", file=sys.stderr)
        return 2
    rows = read_csv(path, dict_rows=True)
    res = classify(rows, load_events(), today, a.days, a.stale, a.company, s["max_followups"],
                   s["thankyou_days"], s["checkin_days"], profile())
    if a.json:
        print(json.dumps(res, indent=1)); return 0
    names = {"followup": f"Follow up (quiet {a.days}+ days, under {s['max_followups']} follow-ups; contract rows by their AB/AC dates)",
             "thankyou": f"Thank-you due (interview in last {s['thankyou_days']} days)",
             "checkin": f"Interviewing, quiet {s['checkin_days']}+ days (check in)",
             "stale": f"Stale ({a.stale}+ days, propose Outcome: No response)",
             "undated": "Applied but no date (fix column G first)"}
    for k, items in res.items():
        print(f"\n## {names[k]}: {len(items)}")
        for x in items:
            when = (f"contacted {x['contacted']} | due {x['due'] or '-'}" if x.get("contract")
                    else f"applied {x['applied'] or '?'}")
            print(f"- row {x['row']} | {x['company']} | {x['title'][:60]} | {x['type'] or '-'} | {when} | "
                  f"quiet {x['days_quiet'] if x['days_quiet'] is not None else '?'}d | follow-ups {x['followups_sent']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Which portals this run searches, in order: search.sources (known ids) + search.extra_portals.

Usage:
  python3 .claude/skills/search-jobs/scripts/sources.py                         # the plan for this profile
  python3 .claude/skills/search-jobs/scripts/sources.py --query "Product Engineer" [--json]

For each portal: display name, whether it needs the candidate signed in (Claude in Chrome), the playbook
section in references/search-workflow.md, and the text for tracker column K (Source). Extra portals get their
search URL filled with the query. Only what's listed here is searched; anything else needs the candidate's say-so.
"""
import argparse, json, os, sys

_d = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(_d, "core", "config.py")) and _d != os.path.dirname(_d):
    _d = os.path.dirname(_d)
sys.path.insert(0, _d)
from core import config  # noqa: E402

# id -> tracker column K text. ATS boards record the employer's own careers page.
SOURCE_LABEL = {
    "linkedin": "LinkedIn", "handshake": "Handshake", "indeed": "Indeed", "glassdoor": "Glassdoor",
    "ashby": "Ashby — official company careers", "greenhouse": "Greenhouse — official company careers",
    "lever": "Lever — official company careers", "wellfound": "Wellfound", "dice": "Dice",
    "ziprecruiter": "ZipRecruiter", "builtin": "Built In", "yc": "YC Work at a Startup (ycombinator.com/jobs)",
    "wttj": "Welcome to the Jungle", "usajobs": "USAJOBS", "weworkremotely": "We Work Remotely",
    "remoteok": "Remote OK", "company_pages": "Company careers page",
}
# id -> heading in references/search-workflow.md
PLAYBOOK = {
    "linkedin": "LinkedIn", "handshake": "Handshake", "indeed": "Indeed", "glassdoor": "Glassdoor",
    "ashby": "Ashby", "greenhouse": "Greenhouse and Lever", "lever": "Greenhouse and Lever",
    "wellfound": "Wellfound", "dice": "Dice", "ziprecruiter": "ZipRecruiter", "builtin": "Built In",
    "yc": "YC Work at a Startup", "wttj": "Welcome to the Jungle", "usajobs": "USAJOBS",
    "weworkremotely": "Remote boards", "remoteok": "Remote boards", "company_pages": "Company career pages",
}


def plan(p, query=""):
    out = []
    for sid in config.sources(p):
        if sid not in config.KNOWN_SOURCES:
            out.append({"id": sid, "name": sid, "known": False, "login_required": None, "playbook": "",
                        "source_label": "", "note": "unknown id: move it to search.extra_portals"})
            continue
        if sid == "dice" and not config.wants_contract(p):
            note = "full-time listings only; contract roles are /search-contract-jobs"
        else:
            note = ""
        out.append({"id": sid, "name": config.KNOWN_SOURCES[sid], "known": True,
                    "login_required": sid in config.LOGIN_SOURCES, "playbook": PLAYBOOK.get(sid, ""),
                    "source_label": SOURCE_LABEL.get(sid, config.KNOWN_SOURCES[sid]), "note": note})
    for x in config.extra_portals(p):
        out.append({"id": "extra", "name": x["name"], "known": False, "login_required": bool(x.get("login_required")),
                    "playbook": "Extra portals", "source_label": x["name"], "url": x.get("url", ""),
                    "search_url": config.search_url(x, query) if query else (x.get("search_url") or x.get("url", "")),
                    "note": x.get("notes", "")})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="List the portals this profile searches.")
    ap.add_argument("--query", default="", help="a title, to fill extra portals' search_url")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    rows = plan(config.load(), a.query)
    if a.json:
        print(json.dumps(rows, indent=1))
        return 0
    for r in rows:
        login = "login" if r["login_required"] else "public" if r["login_required"] is not None else "?"
        extra = f" {r['search_url']}" if r.get("search_url") else ""
        print(f"{r['name']:<32} {login:<6} K={r['source_label']!r:<42} playbook: {r['playbook'] or '-'}{extra}"
              + (f"  ({r['note']})" if r["note"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())

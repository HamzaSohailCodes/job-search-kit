#!/usr/bin/env python3
"""Filter fetched ATS postings down to candidates for the candidate in config/profile.json.

Usage: filter_jobs.py --run-dir DIR --cutoff YYYY-MM-DD --existing existing.csv [--existing more.csv|rows.json] [--top 60]

Rules (all from the profile):
  posted on/after --cutoff;
  title: targets.title_include_regex / title_exclude_regex (defaults below) and targets.skip_levels_regex;
  location: config.loc_regex (areas, remote US when allowed, anywhere in the US when relocation_anywhere_us;
            $EXTRA_LOC_OK adds areas for one run); offices only outside the US always drop;
  SPONSOR_BLOCK (scripts/screen.py) only when work_authorization.needs_sponsorship;
  profile/no_sponsor_companies.txt only when modules.h1b is on;
  pay: posted range topping out below pay.floor (hourly rates: below pay.hourly_floor);
  employment type (ATS employmentType / commitment / metadata, else title and text): kept only when it is in
            targets.employment_types; "Not stated" is kept and noted; a contract of unknown kind is kept when any
            contract type is wanted; internships drop. Each kept job carries etype, emp_label (column L), emp_note;
  dedupe against the tracker export(s) and within the run.

--existing takes a CSV whose first columns are "Job Title","Company","Job Link" (tracker A,B,D) or a full
export (A..), or a rows.json from build_rows.py (rows not yet in the export). Writes <run-dir>/kept.json and
prints candidates ranked by a rough heuristic (the final pick is a judgment call; gate.py scores properly).
"""
import argparse, csv, datetime, html, json, os, re, sys

_d = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(_d, "core", "config.py")) and _d != os.path.dirname(_d):
    _d = os.path.dirname(_d)
sys.path.insert(0, _d)
sys.path.insert(0, os.path.join(_d, "scripts"))
from core import config  # noqa: E402
import screen  # noqa: E402

norm, is_dup, SPONSOR_BLOCK, SPONSOR_OK = screen.norm, screen.is_dup, screen.SPONSOR_BLOCK, screen.SPONSOR_OK

DEFAULT_TITLE = r"engineer|developer"
DEFAULT_NOT = r"\bintern|junior|\bjr\b|new grad|graduate|entry[- ]level|apprentice|\bi\b$|engineer i\b(?!i)|level 1"
NONUS = config.non_us_regex()
PAY_RE = re.compile(r"\$\s*(\d{2,3})(?:[,.]\d{3}|\s*k)", re.I)


def clean(t):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", t or ""))).strip()


def load_existing(paths):
    pairs, urls = [], set()
    for p in paths:
        p = os.path.expanduser(p)
        if p.endswith(".json"):  # build_rows.py output: [title, company, loc, link, ...]
            rows = [(r[0], r[1], r[3]) for r in json.load(open(p))]
        else:
            rows = list(csv.reader(open(p, encoding="utf-8")))
            hdr = [h.strip().lower() for h in (rows[0] if rows else [])]
            li = hdr.index("job link") if "job link" in hdr else 2
            rows = [(r[0], r[1], r[li] if len(r) > li else "") for r in rows[1:] if len(r) > 1]
        for r in rows:
            pairs.append((norm(r[1]), norm(r[0])))
            if r[2]:
                urls.add(r[2].strip())
    return pairs, urls


def gh_type(j):
    """Greenhouse has no standard type field; many boards add it as metadata ('Employment Type': 'Full-time')."""
    for m in j.get("metadata") or []:
        if re.search(r"employment|job type|commitment|worker type|time type", str(m.get("name", "")), re.I):
            v = m.get("value")
            return " ".join(v) if isinstance(v, list) else str(v or "")
    return ""


def pay_numbers(comp):
    return [int(n) * 1000 for n in PAY_RE.findall(comp or "")]


class Filter:
    def __init__(self, p, cutoff, existing_pairs=(), existing_urls=()):
        self.p, self.cutoff = p, cutoff
        self.title, self.not_title = config.title_regexes(p, DEFAULT_TITLE, DEFAULT_NOT)
        lv = config.get(p, "targets.skip_levels_regex", "")
        self.levels = re.compile(lv, re.I) if lv else None
        self.locok = config.loc_regex(p)
        self.remote_ok = config.get(p, "locations.remote_us_ok", True)
        self.needs = config.needs_sponsorship(p)
        self.floor = config.pay_floor(p)
        self.hourly_floor = float(config.get(p, "pay.hourly_floor", 0) or 0)
        self.ex, self.exurl = list(existing_pairs), set(existing_urls)
        self.seen, self.stats, self.out = set(), {}, []

    def bump(self, k):
        self.stats[k] = self.stats.get(k, 0) + 1

    def consider(self, src, co, title, loc, url, date, desc, comp="", remote=False, etype_raw=""):
        self.bump("total")
        if date and date < self.cutoff: return self.bump("old")
        if not self.title.search(title) or self.not_title.search(title) or (self.levels and self.levels.search(title)):
            return self.bump("title")
        us_remote = self.remote_ok and (remote or re.search(r"remote", loc, re.I)) and not NONUS.search(loc)
        first = loc.split("|")[0]
        if not ((self.locok.search(loc) and not NONUS.search(first)) or us_remote): return self.bump("loc")
        if re.search(r"remote", loc, re.I) and NONUS.search(loc) and not (
                self.locok.pattern and self.locok.search(re.sub(r"(?i)remote", "", loc)) or re.search(r"united states|\bus\b|usa", loc, re.I)):
            return self.bump("loc")
        if self.needs and SPONSOR_BLOCK.search(desc): return self.bump("sponsor")
        if screen.is_no_sponsor(co, self.p): return self.bump("no_sponsor_list")
        etype = screen.employment_type(etype_raw, title, desc)
        keep, emp_label, emp_note = screen.type_decision(etype, self.p)
        if not keep: return self.bump("employment_type")
        hr = screen.hourly_top(comp)
        if hr is not None:
            if self.hourly_floor and hr < self.hourly_floor: return self.bump("pay_below_hourly_floor")
        else:
            pay = pay_numbers(comp)
            if self.floor and pay and max(pay) < self.floor: return self.bump("pay_below_floor")
        if url in self.exurl or is_dup(norm(co), norm(title), self.ex): return self.bump("dup_tracker")
        key = (norm(co), norm(title))
        if key in self.seen: return self.bump("dup_run")
        self.seen.add(key)
        yrs = max([int(y) for y in re.findall(r"(\d{1,2})\+?\s*(?:-\s*\d+\s*)?years", desc) if int(y) < 20] or [0])
        o = dict(src=src, co=co, title=title.strip(), loc=loc[:120], url=url, date=date, comp=comp, yrs=yrs,
                 spon_ok=bool(SPONSOR_OK.search(desc)), desc=desc[:6000],
                 etype=etype, emp_label=emp_label, emp_note=emp_note)
        o["h"] = heuristic(o, self.p)
        self.out.append(o)


def heuristic(o, p):
    t, s = o["title"].lower(), 0
    if any(x.lower() in t for x in config.get(p, "targets.titles", []) or []): s += 25
    if re.search(r"\b(senior|sr)\b", t) and config.get(p, "current_role.level", "") == "senior": s += 10
    if config.needs_sponsorship(p) and o["spon_ok"]: s += 15
    stack = config.get(p, "targets.primary_stack_regex", "")
    if stack and re.search(stack, o["desc"], re.I): s += 10
    mx = config.get(p, "targets.max_years_required", 0) or 0
    if mx and o["yrs"] and o["yrs"] > mx: s -= 15
    nums, floor = pay_numbers(o["comp"]), config.pay_floor(p)
    if nums and floor and max(nums) >= floor * 1.25: s += 10
    elif nums and floor and max(nums) < floor * 1.06: s -= 10
    return s


def run(f, D):
    def load(name):
        path = os.path.join(D, name)
        return json.load(open(path)) if os.path.exists(path) else {}

    for s, jobs in load("ashby_boards.json").items():
        for j in jobs:
            if not j.get("isListed", True): continue
            L = [j.get("location") or ""] + [x.get("location", "") for x in (j.get("secondaryLocations") or [])]
            f.consider("Ashby", s, j["title"], " | ".join(L), j["jobUrl"], (j.get("publishedAt") or "")[:10],
                       j.get("descriptionPlain") or "", ((j.get("compensation") or {}).get("compensationTierSummary") or ""),
                       j.get("isRemote") or j.get("workplaceType") == "Remote", j.get("employmentType") or "")
    for s, jobs in load("gh_boards.json").items():
        for j in jobs:
            f.consider("Greenhouse", j.get("company_name") or s, j["title"], (j.get("location") or {}).get("name", ""),
                       j["absolute_url"], (j.get("first_published") or j.get("updated_at") or "")[:10], clean(j.get("content")),
                       etype_raw=gh_type(j))
    for s, jobs in load("lever_boards.json").items():
        for j in jobs:
            d = datetime.datetime.fromtimestamp(j.get("createdAt", 0) / 1000, datetime.timezone.utc).strftime("%Y-%m-%d")
            c = j.get("categories", {}); loc = " | ".join(c.get("allLocations") or [c.get("location", "")])
            f.consider("Lever", s, j["text"], loc + (" | Remote" if j.get("workplaceType") == "remote" else ""), j["hostedUrl"], d,
                       (j.get("descriptionPlain") or "") + " " + " ".join(clean(x.get("content", "")) for x in j.get("lists", [])),
                       etype_raw=c.get("commitment") or "")
    f.out.sort(key=lambda o: (-o["h"], o["co"].lower(), o["title"]))
    return f.out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Filter fetched ATS postings with the candidate's profile.")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--cutoff", required=True, help="keep postings published on/after this date")
    ap.add_argument("--existing", action="append", default=[], help="tracker export CSV or prior rows.json (repeatable)")
    ap.add_argument("--top", type=int, default=60)
    a = ap.parse_args(argv)
    D = os.path.expanduser(a.run_dir)
    p = config.load()
    if not a.existing:
        print("WARNING: no --existing tracker export; dedupe against the sheet is OFF")
    EX, EXURL = load_existing(a.existing)
    f = Filter(p, a.cutoff, EX, EXURL)
    out = run(f, D)
    json.dump(out, open(os.path.join(D, "kept.json"), "w"))
    print(f.stats, "kept", len(out))
    print(f"\nTop {min(a.top, len(out))} by heuristic (h | posted | src | company | title | location | comp | yrs | sponsor):")
    for o in out[:a.top]:
        print(f"{o['h']:3d} | {o['date']} | {o['src'][:2]} | {o['co'][:22]} | {o['title'][:62]} | {o['loc'][:40]} | "
              f"{o['comp'][:28]} | y{o['yrs']} | {o['emp_label']}{' | SPON+' if o['spon_ok'] and f.needs else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

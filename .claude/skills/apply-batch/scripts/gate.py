#!/usr/bin/env python3
"""Must-have gate for a posting: PASS / WARN / FAIL with reasons, plus a 0-100 match score.
Run it before anything is shortlisted or filled. A FAIL is a knockout; WARN items go into the pick table.

Every rule comes from config/profile.json:
  knockouts   US citizenship required (unless the candidate is a citizen), security clearance (unless
              work_authorization.security_clearance is set), "states no sponsorship" (only when
              work_authorization.needs_sponsorship), company on profile/no_sponsor_companies.txt (modules.h1b)
  levels      targets.skip_levels_regex on the title
  years       more than targets.max_years_required asked (WARN above current_role.years_experience)
  stack       targets.primary_stack_regex (WARN when absent), targets.other_stack_knockouts (FAIL when the
              posting leads with one and never names the primary stack, WARN otherwise)
  domain      targets.domain_skips
  location    offices only outside the US (config.non_us_regex); outside the candidate's areas (config.loc_regex)
              when not remote and not relocation_anywhere_us
  pay         posted range topping out below config.pay_floor (hourly rates: below pay.hourly_floor)
  work type   column-L label (or detected type) not in targets.employment_types

Score weights: stack 30, tools 10, scope 10, domain 10, seniority 10, location 10, pay 5, sponsorship 15.
Tools = targets.skills.core + targets.skills.ai named in the posting. Scope = targets.scope_regex and domain =
targets.domain_prefer_regex when set (neutral otherwise). Sponsorship is full marks when the candidate doesn't
need it; with modules.h1b on it follows the filing history (sponsors 15, some 9, unknown 6, none 3).

Usage:
  python3 gate.py --kept <run>/kept.json [--h1b]                   # writes <run>/gated.json
  python3 gate.py --tracker tracker/tracker.csv --rows 481,487 [--h1b]
  from gate import gate, score
  gate(title, desc, location, comp, company=...) -> {'verdict','fails','warns','primary_stack','scope'}
--h1b is ignored (with a note) when modules.h1b is off. The H-1B result is evidence, never a FAIL by itself.
"""
import argparse, csv, json, os, re, sys

_d = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(_d, "core", "config.py")) and _d != os.path.dirname(_d):
    _d = os.path.dirname(_d)
sys.path.insert(0, _d)
sys.path.insert(0, os.path.join(_d, "scripts"))
from core import config  # noqa: E402
import screen  # noqa: E402

csv.field_size_limit(10 ** 8)

CITIZEN_REQ = r"\b(us|u\.s\.) citizen(ship)? (is )?required|must be (a )?(us|u\.s\.) citizen|citizenship (is )?required|(us|u\.s\.) citizens only"
CLEARANCE_REQ = r"security clearance|ts/sci|top secret|secret clearance|clearance (is )?required|active clearance"
EXPORT_CTRL = r"\bitar\b|export control"
NO_SPONSOR = (r"\b(no|not) (visa )?sponsorship|unable to sponsor|cannot sponsor|will not sponsor|not able to sponsor|"
              r"without (the need for )?(visa )?sponsorship\b.{0,30}required|must be authorized .{0,40}without sponsorship")
YEARS = r"(\d{1,2})\+?\s*(?:(?:-|to)\s*\d+\s*)?years?\s+(?:of\s+)?(?:\w+\s+){0,3}experience"
US_HINT = (r"united states|\busa?\b|remote|, ?(a[klzr]|c[aot]|de|fl|ga|hi|i[adln]|k[sy]|la|m[adeinost]|n[cdehjmvy]|"
           r"o[hkr]|pa|ri|s[cd]|t[nx]|ut|v[at]|w[aivy]|dc)\b")
STATE_LIMITS = r"(must|only) (reside|be located|live) in|eligible states|following states|not (currently )?hiring in"


def _profile(p=None):
    return p if p is not None else (config.load(required=False) or config._example_defaults())


def _is_citizen(p):
    return bool(re.search(r"united states|^\s*(us|usa|u\.s\.a?\.?)\s*$|american", config.get(p, "work_authorization.citizenship", "") or "", re.I))


def _stack(p):
    s = config.get(p, "targets.primary_stack_regex", "") or ""
    return re.compile(s, re.I) if s else None


def _others(p):
    return [(re.compile(k.get("regex", ""), re.I), k.get("label", k.get("regex", ""))) for k in config.get(p, "targets.other_stack_knockouts", []) or [] if k.get("regex")]


def _tops(comp):
    if re.search(r"not listed|verify|unknown", (comp or "").lower()):
        return []
    out = []
    for a, b in re.findall(r"\$\s?(\d{2,3})(?:,(\d{3}))?\s?k?", comp or ""):
        v = int(a + (b or ""))
        out.append(v * 1000 if v < 1000 else v)
    return out


def years_asked(d):
    return [int(y) for y in re.findall(YEARS, d) if int(y) < 30]


def _loc_class(loc, p):
    """'' (no location), 'non-US', 'outside areas', or 'ok'."""
    if not loc:
        return ""
    if config.non_us_regex().search(loc) and not re.search(US_HINT, loc):
        return "non-US"
    if re.search(r"remote", loc) and config.get(p, "locations.remote_us_ok", True):
        return "ok"
    if config.get(p, "locations.relocation_anywhere_us"):
        return "ok"
    rest = re.sub(r"remote", "", loc).strip(" |,-()")
    if rest and config.loc_regex(p).search(rest):
        return "ok"
    return "outside areas"


def primary_stack(d, p=None):
    st = _stack(_profile(p))
    if not st:
        return "unspecified"
    hits = st.findall(d)
    return "primary" if hits else "other" if any(r.search(d) for r, _ in _others(_profile(p))) else "not stated"


def gate(title, desc, location="", comp="", pay_floor=None, posted_days=None, company="", p=None, employment=""):
    """employment: the tracker's column-L label ('Full-time', 'Contract (C2C)', 'Not stated') or an ATS type;
    empty -> detected from the title and description."""
    p = _profile(p)
    t = (title or "").lower()
    d = re.sub(r"\s+", " ", (desc or "")).lower()
    loc = (location or "").lower()
    td = t + " " + d
    fails, warns = [], []
    needs = config.needs_sponsorship(p)

    # knockouts
    if re.search(CITIZEN_REQ, td) and not _is_citizen(p):
        fails.append("citizenship required")
    if re.search(CLEARANCE_REQ, td) and not config.get(p, "work_authorization.security_clearance", ""):
        fails.append("security clearance required")
    if re.search(EXPORT_CTRL, td) and not _is_citizen(p):
        (fails if needs else warns).append("export-control (ITAR) role: US persons only")
    if needs and (re.search(NO_SPONSOR, td) or screen.SPONSOR_BLOCK.search(td)):
        fails.append("states no sponsorship")
    if needs and company and screen.is_no_sponsor(company, p):
        fails.append("company said it does not sponsor (profile/no_sponsor_companies.txt)")
    lv = config.get(p, "targets.skip_levels_regex", "")
    if lv and re.search(lv, t, re.I):
        fails.append("level excluded by targets.skip_levels_regex (title)")
    yrs = years_asked(d)
    mx_req = config.get(p, "targets.max_years_required", 0) or 0
    have = config.get(p, "current_role.years_experience", 0) or 0
    if yrs and mx_req and max(yrs) > mx_req:
        fails.append(f"{max(yrs)}+ years of experience asked (max {mx_req})")
    elif yrs and have and max(yrs) > have:
        warns.append(f"{max(yrs)}+ years asked (candidate has {have})")
    cleared = bool(config.get(p, "work_authorization.security_clearance", ""))
    for item in config.get(p, "targets.domain_skips", []) or []:
        rx, label = item.get("regex"), item.get("label") or "domain"
        if not rx or not re.search(rx, td, re.I):
            continue
        if label.lower() == "clearance":
            if not cleared and "security clearance required" not in fails:
                fails.append("security clearance required")
            continue
        fails.append(f"domain skip: {label}")

    # stack
    st = _stack(p)
    st_hit = bool(st and st.search(d))
    for rx, label in _others(p):
        if rx.search(d):
            (warns if st_hit else fails).append(f"{label} stack" + ("" if st_hit else " and no primary stack named" if st else ""))
    lang = primary_stack(d, p)
    if st and not st_hit and lang == "not stated":
        warns.append("primary stack not mentioned")

    # location
    lc = _loc_class(loc, p)
    if lc == "non-US":
        fails.append(f"office outside the US: {location}")
    elif lc == "outside areas":
        fails.append(f"office outside the candidate's areas: {location}")
    if re.search(r"remote", loc) and re.search(STATE_LIMITS, d):
        warns.append(f"remote with state restrictions: check {config.get(p, 'identity.state', '') or 'your state'} is eligible")

    # work type
    et = config.employment_type_of(employment) if employment and employment.lower() != "not stated" else ""
    if not et and employment.lower() != "not stated":
        et = screen.employment_type(employment, title, desc)
    keep, _, note = screen.type_decision(et, p)
    if not keep:
        fails.append(f"work type not wanted ({config.employment_label(et) if et in config.EMPLOYMENT_TYPES else et}); see targets.employment_types")
    elif note and et:  # "not stated" is common and only noted in column I; a contract of unknown kind is worth a look
        warns.append(note)

    # pay
    hr = screen.hourly_top(comp)
    hfloor = float(config.get(p, "pay.hourly_floor", 0) or 0)
    floor = config.pay_floor(p) if pay_floor is None else pay_floor
    tops = [] if hr is not None else _tops(comp)
    if hr is not None and hfloor and hr < hfloor:
        fails.append(f"rate tops out below ${hfloor:g}/hr: {comp}")
    if floor and tops and max(tops) < floor:
        fails.append(f"pay tops out below ${floor:,}: {comp}")

    # scope and freshness
    scope_rx = config.get(p, "targets.scope_regex", "")
    scope = bool(scope_rx and re.search(scope_rx, td, re.I))
    if scope_rx and not scope:
        warns.append("none of the target scope words (targets.scope_regex)")
    if len(d) < 1500:
        warns.append("short/truncated description: read the posting before deciding")
    if posted_days is not None and posted_days > 120:
        warns.append(f"posting is {posted_days} days old: may be filled or stale")
    if re.search(r"\bfounding\b", t) and not re.search(r"from scratch|0-to-1|zero to one|from the ground up", d):
        warns.append("founding role: expects a 0-to-1 track record; lead with from-scratch builds or skip")
    verdict = "FAIL" if fails else "WARN" if warns else "PASS"
    return {"verdict": verdict, "fails": fails, "warns": warns, "primary_stack": lang, "scope": scope}


def _tool_patterns(p):
    terms = (config.get(p, "targets.skills.core", []) or []) + (config.get(p, "targets.skills.ai", []) or [])
    out = []
    for term in dict.fromkeys(t.strip().lower() for t in terms if t and t.strip()):
        out.append((term, re.compile(r"(?<![\w.])" + re.escape(term).replace(r"\.", r"\.?") + r"(?![\w])", re.I)))
    return out


def score(title, desc, location="", comp="", h1b_verdict=None, large_company=False, p=None):
    p = _profile(p)
    t = (title or "").lower()
    d = re.sub(r"\s+", " ", (desc or "")).lower()
    td = t + " " + d
    loc = (location or "").lower()
    b = {}
    # stack (30)
    st = _stack(p)
    st_n = len(st.findall(d)) if st else 0
    other = any(rx.search(d) for rx, _ in _others(p))
    if not st: b["stack"] = 15
    elif st_n >= 2 or (st_n >= 1 and not other): b["stack"] = 30
    elif st_n >= 1: b["stack"] = 22
    elif other: b["stack"] = 0
    else: b["stack"] = 12
    # tools named on the resume (10)
    hits = [term for term, rx in _tool_patterns(p) if rx.search(d)]
    b["tools"] = min(10, 2 * len(hits))
    # scope (10) and domain (10): neutral unless the profile says what it wants
    sc = config.get(p, "targets.scope_regex", "")
    b["scope"] = (10 if re.search(sc, td, re.I) else 4) if sc else 7
    dm = config.get(p, "targets.domain_prefer_regex", "")
    b["domain"] = (10 if re.search(dm, td, re.I) else 6) if dm else 7
    # seniority (10)
    yrs = years_asked(d)
    mx = max(yrs) if yrs else None
    have = config.get(p, "current_role.years_experience", 0) or 0
    mx_req = config.get(p, "targets.max_years_required", 0) or 0
    lv = config.get(p, "targets.skip_levels_regex", "")
    if lv and re.search(lv, t, re.I): b["seniority"] = 0
    elif mx is None: b["seniority"] = 8
    elif not have or mx <= have: b["seniority"] = 10
    elif not mx_req or mx <= mx_req: b["seniority"] = 5
    else: b["seniority"] = 0
    # location (10)
    lc = _loc_class(loc, p)
    b["location"] = {"": 6, "non-US": 0, "outside areas": 3}.get(lc, 10)
    # pay (5) vs the candidate's ask
    hr = screen.hourly_top(comp)
    hfloor = float(config.get(p, "pay.hourly_floor", 0) or 0)
    tops = [] if hr is not None else _tops(comp)
    top = max(tops) if tops else None
    floor = config.pay_floor(p)
    ask = config.get(p, "pay.ask_when_no_range", 0) or int(floor * 1.25)
    if hr is not None: b["pay"] = 3 if not hfloor else 5 if hr >= hfloor * 1.2 else 4 if hr >= hfloor else 2
    elif top is None or not ask: b["pay"] = 3
    elif top >= ask: b["pay"] = 5
    elif top >= (floor + ask) / 2: b["pay"] = 4
    else: b["pay"] = 2
    # sponsorship evidence (15)
    if not config.needs_sponsorship(p):
        b["sponsorship"] = 15
    elif h1b_verdict is not None:
        b["sponsorship"] = {"sponsors": 15, "some": 9}.get(h1b_verdict, (0 if large_company else 3) if h1b_verdict == "none" else 6)
    else:
        b["sponsorship"] = 15 if screen.SPONSOR_OK.search(d) else 6
    b["total"] = sum(b.values())
    b["tools_hit"] = hits
    return b


TIER = {"sponsors": 0, "some": 1, None: 2, "unknown": 2, "none": 3}


def run(items, p, h1b=None):
    """items: [(company, title, desc, location, comp, src_dict)] -> list of gate results (sorted when h1b)."""
    out = []
    for co, title, desc, loc, comp, src in items:
        g = gate(title, desc, loc, comp, company=co, p=p, employment=(src or {}).get("employment", ""))
        if h1b:
            h = h1b["lookup"](co)
            g["h1b"] = h["verdict"]
            g["h1b_recent"] = h.get("count_recent", 0)
            g["h1b_evidence"] = h1b["evidence"](h)
            if h["verdict"] == "none":
                g["warns"].append("no H-1B filing history: rank below known sponsors; ask about sponsorship in the first reply")
                if g["verdict"] == "PASS":
                    g["verdict"] = "WARN"
        sc = score(title, desc, loc, comp, g.get("h1b"), p=p)
        g["score"] = sc["total"]
        g["score_breakdown"] = {k: v for k, v in sc.items() if k not in ("total", "tools_hit")}
        g["tools_hit"] = sc["tools_hit"]
        g.update({"company": co, "title": title, "src": src})
        out.append(g)
    if h1b:
        out.sort(key=lambda g: (TIER.get(g.get("h1b"), 2), -g["score"]))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="PASS/WARN/FAIL gate and match score for postings.")
    ap.add_argument("--kept", help="kept.json from filter_jobs.py (or any list of {co,title,desc,loc,comp})")
    ap.add_argument("--tracker", help="tracker export CSV (A title, B company, C location, E pay, N description)")
    ap.add_argument("--rows", default="", help="tracker row numbers, comma-separated (header = row 1)")
    ap.add_argument("--h1b", action="store_true", help="add H-1B filing history per company (modules.h1b only)")
    a = ap.parse_args(argv)
    p = config.load()
    items = []
    if a.kept:
        for j in json.load(open(a.kept)):
            items.append((j.get("co") or j.get("company") or "", j.get("title", ""), j.get("desc", ""),
                          j.get("loc") or j.get("location", ""), j.get("comp", ""),
                          {"url": j.get("url", ""), "employment": j.get("emp_label") or j.get("type", "")}))
    if a.tracker:
        rows = list(csv.reader(open(a.tracker, encoding="utf-8")))
        want = {int(x) for x in a.rows.split(",") if x.strip()}
        for i, r in enumerate(rows[1:], start=2):
            if not want or i in want:
                r = r + [""] * 29  # older exports stop at Q or R
                items.append((r[1], r[0], r[13], r[2], r[4], {"row": i, "employment": r[11]}))
    h1b = None
    if a.h1b and not config.module_on(p, "h1b"):
        print("note: modules.h1b is off in config/profile.json; skipping the H-1B lookup")
    elif a.h1b:
        sys.path.insert(0, config.path("modules", "h1b"))
        import h1b_lookup  # noqa: E402
        h1b = {"lookup": h1b_lookup.lookup, "evidence": h1b_lookup.evidence}
    out = run(items, p, h1b)
    for g in out:
        bd = g["score_breakdown"]
        extra = f" | h1b={g['h1b']}({g.get('h1b_recent', 0)})" if h1b else ""
        print(f"{g['verdict']:<4} {g['score']:>3} {g['company'][:20]:<20} {g['title'][:36]:<36} st{bd['stack']} tl{bd['tools']} "
              f"sc{bd['scope']} do{bd['domain']} sn{bd['seniority']} lo{bd['location']} pa{bd['pay']} sp{bd['sponsorship']}{extra} | "
              + "; ".join(g["fails"] + g["warns"])[:110])
    if h1b:
        print("\n(sorted: sponsors > some > unknown > none, then score)")
    if a.kept:
        dst = os.path.join(os.path.dirname(os.path.abspath(a.kept)), "gated.json")
        json.dump(out, open(dst, "w"), indent=1)
        print(f"\n{len(out)} gated -> {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Check a list of companies (e.g. from a curated "companies hiring" post) for roles that fit the candidate.

Usage: company_list.py --list companies.txt --out DIR --existing tracker.csv [--existing rows.json ...]

companies.txt: one company per line, "Name: careers-url" or "Name - careers-url" or just "Name".
For each company: look for Ashby/Greenhouse/Lever/Kula links on the careers page, else guess slugs from the
name/domain against the Ashby, Greenhouse and Lever APIs. Nothing about companies is stored: the list comes
fresh from each post. Writes DIR/roles.json (matching roles + fit/sponsor/tracker flags) and prints a
per-company summary plus companies that need a browser check (JS-rendered pages: Comeet, Darwinbox...).

Filters come from config/profile.json: title include/exclude regexes, locations (config.loc_regex), work type
(targets.employment_types; each role carries emp_label for column L),
sponsorship wording only when work_authorization.needs_sponsorship, the no-sponsor list only when modules.h1b.
--existing: tracker export CSV with columns A..D or more (title, company, location, link, pay, status), or a
build_rows.py rows.json.
"""
import argparse, csv, html, json, os, re, sys, urllib.request, concurrent.futures as cf

_d = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(_d, "core", "config.py")) and _d != os.path.dirname(_d):
    _d = os.path.dirname(_d)
sys.path.insert(0, _d)
sys.path.insert(0, os.path.join(_d, "scripts"))
from core import config  # noqa: E402
import screen  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (Macintosh) Chrome/128"}
DEFAULT_ENG = r"engineer|developer|full[- ]?stack|software|forward deployed|deployment|solutions architect|member of technical staff"
DEFAULT_NOT = r"\bintern|junior|new grad|sales|account exec|nurse|recruiter"
US_HINT = re.compile(r"united states|\busa?\b|, ?(a[klzr]|c[aot]|de|fl|ga|hi|i[adln]|k[sy]|la|m[adeinost]|n[cdehjmvy]|o[hkr]|pa|ri|s[cd]|t[nx]|ut|v[at]|w[aivy]|dc)\b", re.I)


def get(u, js=False):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=20) as r:
            b = r.read().decode("utf-8", "ignore")
            return json.loads(b) if js else b
    except Exception:
        return None


def clean(t):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", (t or "").replace("\\u003c", "<").replace("\\u003e", ">")))).strip()


def title_filters(p):
    inc, exc = config.title_regexes(p, DEFAULT_ENG, DEFAULT_NOT)
    lv = config.get(p, "targets.skip_levels_regex", "")
    return inc, exc, (re.compile(lv, re.I) if lv else None)


def title_ok(t, p):
    inc, exc, lv = title_filters(p)
    return bool(inc.search(t)) and not exc.search(t) and not (lv and lv.search(t))


def board(kind, slug, title_filter=None):
    """All postings on one public board as dicts (t, loc, url, date, remote, comp, desc), or None if no board.
    title_filter(title) -> bool skips non-matching Kula postings before fetching each page."""
    if kind == "ashby":
        a = get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true", True)
        if not a or a.get("jobs") is None: return None
        return [dict(t=j["title"], loc=" | ".join([j.get("location") or ""] + [x.get("location", "") for x in j.get("secondaryLocations") or []]),
                     url=j["jobUrl"], date=(j.get("publishedAt") or "")[:10], remote=bool(j.get("isRemote")),
                     comp=((j.get("compensation") or {}).get("compensationTierSummary") or "").split("•")[0].strip(),
                     desc=(j.get("descriptionPlain") or "")[:6000], etype=j.get("employmentType") or "")
                for j in a["jobs"] if j.get("isListed", True)]
    if kind == "greenhouse":
        g = get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true", True)
        if not g or g.get("jobs") is None: return None
        return [dict(t=j["title"], loc=(j.get("location") or {}).get("name", ""), url=j["absolute_url"],
                     date=(j.get("first_published") or j.get("updated_at") or "")[:10], remote=False, comp="",
                     desc=clean(html.unescape(j.get("content") or ""))[:6000]) for j in g["jobs"]]
    if kind == "lever":
        l = get(f"https://api.lever.co/v0/postings/{slug}?mode=json", True)
        if not isinstance(l, list): return None
        return [dict(t=j["text"], loc=" | ".join(j.get("categories", {}).get("allLocations") or [j.get("categories", {}).get("location", "")]),
                     url=j["hostedUrl"], date="", remote=j.get("workplaceType") == "remote", comp="",
                     desc=(j.get("descriptionPlain") or "")[:6000], etype=(j.get("categories") or {}).get("commitment") or "") for j in l]
    if kind == "kula":
        h = get(f"https://careers.kula.ai/{slug}")
        if not h: return None
        out = []
        for path in sorted(set(re.findall(rf"/{re.escape(slug)}/\d+-[\w-]+", h))):
            title = re.sub(r"^\d+-", "", path.split("/")[-1]).replace("-", " ").title()
            if title_filter and not title_filter(title): continue
            raw = get("https://careers.kula.ai" + path) or ""
            ld = re.search(r'"@type":"JobPosting".*?"description":"(.*?)","(?:datePosted|employmentType|hiringOrganization|title)"', raw, re.S)
            d = clean(ld.group(1).encode().decode("unicode_escape", "ignore")) if ld else clean(raw)
            city = re.search(r'"addressLocality":"([^"]+)"', raw); ctry = re.search(r'"addressCountry":"([^"]+)"', raw)
            full = clean(raw)
            mode = re.search(r"Workplace:\s*(Remote|Hybrid|On-?Site|Onsite)", full, re.I) or ("TELECOMMUTE" in raw and re.search(r"(Remote)", "Remote"))
            pay = re.search(r"(USD|\$)\s?[\d,]+\s?-\s?[\d,]+", full)
            loc = ", ".join(x.group(1) for x in (city, ctry) if x) + (f" ({mode.group(1)})" if mode else "")
            posted = re.search(r'"datePosted":"([\d-]{10})', raw)
            out.append(dict(t=title, loc=loc, url="https://careers.kula.ai" + path, date=posted.group(1) if posted else "",
                            remote=bool(re.search(r"remote", loc, re.I)), comp=pay.group(0) if pay else "", desc=d[:6000]))
        return out
    return None


def discover(name, url):
    if url:
        h = get(url if url.startswith("http") else "https://" + url) or ""
        for kind, rx in [("ashby", r"jobs\.ashbyhq\.com/([\w.-]+)"), ("greenhouse", r"(?:job-)?boards(?:-api)?\.greenhouse\.io/(?:embed/job_board\?for=|v1/boards/)?([\w-]+)"),
                         ("lever", r"jobs\.lever\.co/([\w.-]+)"), ("kula", r"careers\.kula\.ai/([\w-]+)")]:
            for slug in re.findall(rx, h):
                if slug.lower() in ("embed", "v1", "jobs"): continue
                if board(kind, slug) is not None: return [kind, slug]
        if re.search(r"comeet|darwinbox|workday|rippling|bamboohr|workable|icims", h, re.I): return ["browser", url]
    base = re.sub(r"[^a-z0-9 ]", "", name.lower()).strip()
    dom = re.sub(r"^(https?://)?(www\.)?", "", url or "").split("/")[0].split(".")[0]
    for slug in dict.fromkeys([base.replace(" ", ""), base.replace(" ", "-"), base.split(" ")[0] if base else "", dom]):
        if not slug: continue
        for kind in ("ashby", "greenhouse", "lever"):
            if board(kind, slug): return [kind, slug]
    return ["browser", url] if url else None


def parse_list(lines):
    comps = []
    for line in lines:
        line = line.strip().lstrip("-•* ")
        if not line: continue
        m = re.match(r"(.+?)\s*[:\-–]\s*((?:https?://)?[\w.-]+\.[a-z]{2,}(?:/\S*)?)\s*$", line)
        comps.append((m.group(1).strip(), m.group(2)) if m else (line, ""))
    return comps


def loc_fit(loc, remote, p):
    """'Target area' | 'Remote US' | 'non-US' | 'US other'."""
    if config.non_us_regex().search(loc) and not US_HINT.search(loc):
        return "non-US"
    rest = re.sub(r"(?i)remote", "", loc).strip(" |,-()")
    if rest and config.loc_regex(p).search(rest):  # matches any US place when relocation_anywhere_us
        return "Target area"
    if (remote or re.search(r"remote", loc, re.I)) and config.get(p, "locations.remote_us_ok", True):
        return "Remote US"
    return "US other"


def load_existing(paths):
    T = []
    for p in paths:
        if p.endswith(".json"):
            T += [(r[0], r[1], r[3], r[5] if len(r) > 5 else "") for r in json.load(open(p))]
        else:
            for r in list(csv.reader(open(p, encoding="utf-8")))[1:]:
                if len(r) > 5: T.append((r[0], r[1], r[3], r[5]))
                elif len(r) > 2: T.append((r[0], r[1], r[2], r[3] if len(r) > 3 else ""))
    return T


def main(argv=None):
    ap = argparse.ArgumentParser(description="Find fitting roles at a list of companies.")
    ap.add_argument("--list", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--existing", action="append", default=[])
    a = ap.parse_args(argv); os.makedirs(a.out, exist_ok=True)
    p = config.load()
    needs = config.needs_sponsorship(p)
    comps = parse_list(open(a.list, encoding="utf-8"))
    T = load_existing(a.existing)

    def work(c):
        name, url = c
        k = discover(name, url)
        jobs = board(*k, title_filter=lambda t: title_ok(t, p)) if k and k[0] != "browser" else None
        return name, url, k, jobs or []
    with cf.ThreadPoolExecutor(10) as ex:
        res = list(ex.map(work, comps))

    roles, browser, none = [], [], []
    for name, url, k, jobs in res:
        if not k or k[0] == "browser":
            browser.append(f"{name} ({(k or [None, url])[1] or 'no careers url'})"); continue
        key = (screen.norm(name).split() or [""])[0]
        trk = [t for t in T if key and key in screen.norm(t[1])]
        status = sorted({t[3] for t in trk if t[3]})
        hits = 0
        for j in jobs:
            if not title_ok(j["t"], p): continue
            fit = loc_fit(j["loc"], j["remote"], p)
            if fit in ("non-US", "US other"): continue
            keep, emp_label, emp_note = screen.type_decision(screen.employment_type(j.get("etype", ""), j["t"], j["desc"]), p)
            if not keep: continue
            hits += 1
            roles.append(dict(company=name, board=k, title=j["t"], loc=j["loc"], fit=fit, url=j["url"], date=j["date"], comp=j["comp"],
                              sponsor_block=needs and bool(screen.SPONSOR_BLOCK.search(j["desc"])),
                              sponsor_ok=needs and bool(screen.SPONSOR_OK.search(j["desc"])),
                              no_sponsor_list=screen.is_no_sponsor(name, p),
                              company_status=status, emp_label=emp_label, emp_note=emp_note,
                              in_tracker=any(t[2] == j["url"] or screen.is_dup(screen.norm(name), screen.norm(j["t"]), [(screen.norm(t[1]), screen.norm(t[0]))]) for t in trk),
                              desc=j["desc"]))
        print(f"{name:24s} {k[0]}/{k[1]}: {len(jobs)} jobs, {hits} matching roles in target areas/remote | tracker: {status or '-'}")
        if not hits: none.append(name)
    json.dump(roles, open(os.path.join(a.out, "roles.json"), "w"))
    print(f"\n{len(roles)} candidate roles -> {a.out}/roles.json")
    for r in roles:
        done = [s for s in r["company_status"] if s in ("Applied", "Interviewing", "Rejected", "Offer", "Skipped")]
        flag = (f"SKIP {done[0].lower()}" if done else "dup" if r["in_tracker"]
                else "NO SPONSOR" if (r["sponsor_block"] or r["no_sponsor_list"]) else "")
        print(f"  [{r['fit']}] {r['company']} | {r['title'][:60]} | {r['emp_label']} | {r['comp'] or '-'} | {r['date'] or '-'} {('| ' + flag) if flag else ''}")
    print("\nNo fitting roles:", ", ".join(none) or "-")
    print("Check in browser (JS-rendered / unknown board):", "; ".join(browser) or "-")
    return 0


if __name__ == "__main__":
    sys.exit(main())

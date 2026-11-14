#!/usr/bin/env python3
"""Shared screening helpers for search-jobs, apply-batch and company_list.

    norm(s)                      company/title normaliser (drops Inc/LLC/punctuation)
    is_dup(co, title, rows)      fuzzy company + title match against [(norm co, norm title), ...]
    SPONSOR_BLOCK / SPONSOR_OK   regexes for "we don't sponsor" / "sponsorship available" wording
    onsite_elsewhere(desc, p)    an on-site/in-office line naming a US city outside the candidate's areas
    okloc(loc, p)                location fits the candidate's areas (config.loc_regex)
    is_no_sponsor(company, p)    company is on profile/no_sponsor_companies.txt (only when modules.h1b is on)
    employment_type(...)         full_time / part_time / contract_* / 'contract' / 'intern' / '' from ATS fields + text
    type_decision(etype, p)      (keep?, column L label, note) against targets.employment_types
    get(url), li_detail(job_id)  polite fetch, LinkedIn guest job-detail parser

CLI (quick checks):
    python3 scripts/screen.py --company "Acme"      # is it on the no-sponsor list?
    python3 scripts/screen.py --text posting.txt    # sponsorship wording found in a saved posting

Data location: the repo root, or $JOB_KIT_DATA if set (tests point it at a temp folder).
Standard library only.
"""
import argparse, html, os, re, sys, time, urllib.error, urllib.request

_d = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(_d, "core", "config.py")) and _d != os.path.dirname(_d):
    _d = os.path.dirname(_d)
sys.path.insert(0, _d)
from core import config  # noqa: E402

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"


def data_root():
    return os.path.abspath(os.path.expanduser(os.environ.get("JOB_KIT_DATA") or config.ROOT))


def _profile(p=None):
    if p is not None:
        return p
    return config.load(required=False) or config._example_defaults()


# --- normalising and dedupe ----------------------------------------------------

def norm(s):
    s = (s or "").lower()
    s = re.sub(r"\b(inc|llc|ltd|corp|corporation|co|the)\b\.?", "", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def is_dup(co, ti, rows):
    """co and ti already normalised; rows = [(norm company, norm title), ...]."""
    a = set(ti.split())
    for eco, eti in rows:
        if not co or not eco or not (co == eco or co in eco or eco in co):
            continue
        b = set(eti.split())
        if ti == eti or (a and b and len(a & b) / len(a | b) >= 0.8):
            return True
    return False


# --- sponsorship wording -----------------------------------------------------------

SPONSOR_BLOCK = re.compile(
    r"(not|unable to|cannot|can ?not|won't|will not|do not|does not|no)\s+(currently\s+)?(offer|provide|sponsor|support)\w*\s+(\w+\s+){0,4}(visa|sponsorship|h-?1b)|"
    r"without (the need for |requiring |need of )?(current or future |future |any )?(visa )?sponsorship|"
    r"no (visa )?sponsorship|sponsorship (is )?not (available|offered|provided)|"
    r"u\.?s\.? citizen(s|ship)? (only|is required|required)|must be a u\.?s\.? citizen|"
    r"green card holders? only|(active|current) (security )?clearance|ts/sci|top secret|secret clearance|"
    r"not (eligible|able) to sponsor|unable to sponsor|will not sponsor|does not sponsor|cannot sponsor|"
    r"not in a position to sponsor|sponsorship (and|or) transfers? (are |is )?not (available|offered|provided|supported)|"
    r"(visa )?(sponsorship|transfers?)[^.]{0,30}(are|is) not (available|offered|provided|supported)|"
    r"unable to provide (visa )?sponsorship|(citizens|citizenship) and (other )?u\.?s\.? persons|"
    r"open only to u\.?s\.? (citizens|persons)|u\.?s\.? persons? only", re.I)
SPONSOR_OK = re.compile(r"(visa|h-?1b) (sponsorship|transfer)s? (is |are )?(available|offered|provided|welcome|supported)|"
                        r"(we|will|can|able to) sponsor|sponsorship available|open to sponsor|h-?1b transfer", re.I)

US_CITIES = (r"san francisco|\bsf\b|seattle|austin|chicago|los angeles|denver|palo alto|mountain view|new york|nyc|"
             r"boston|atlanta|miami|dallas|houston|washington,? d\.?c|san diego|san jose|portland|philadelphia|pittsburgh")
_ONSITE = re.compile(r"(on-?site|in[- ]office|in person)[^.]{0,60}(" + US_CITIES + r")", re.I)


def onsite_elsewhere(desc, p=None):
    """The on-site/in-office phrase when it names a US city outside the candidate's areas, else ''.
    Always '' when the candidate relocates anywhere in the US."""
    p = _profile(p)
    if config.get(p, "locations.relocation_anywhere_us"):
        return ""
    ok = config.loc_regex(p)
    for m in _ONSITE.finditer(desc or ""):
        if not ok.pattern or not ok.search(m.group(2)):
            return m.group(0)
    return ""


def okloc(loc, p=None):
    """True when a location string fits the candidate's areas (or is unspecified / plain 'United States')."""
    l = (loc or "").lower().strip()
    if not l or l == "united states":
        return True
    return bool(config.loc_regex(_profile(p)).search(l))


# --- pay ---------------------------------------------------------------------------

HOURLY = re.compile(r"\$\s*(\d{2,3}(?:\.\d{1,2})?)\s*(?:-|–|to)?\s*(?:\$\s*(\d{2,3}(?:\.\d{1,2})?))?\s*(?:/\s*h(?:ou)?r\b|per hour|an hour|hourly)", re.I)


def hourly_top(comp):
    """Top of an hourly rate ('$70–$90/hr' -> 90.0), or None when the pay isn't hourly."""
    m = HOURLY.search(comp or "")
    if not m:
        return None
    return max(float(x) for x in m.groups() if x)


# --- employment type (tracker column L) ------------------------------------------------

_C2C = re.compile(r"\bc2c\b|corp[- ]to[- ]corp|corp2corp", re.I)
_1099 = re.compile(r"\b1099\b", re.I)
_W2 = re.compile(r"\bw-?2\b", re.I)
_CONTRACT = re.compile(r"\bcontract(or)?\b|\btemporary\b|\btemp\b|fixed[- ]term|contract[- ]to[- ]hire", re.I)
_PART = re.compile(r"\bpart[- ]?time\b", re.I)
_FULL = re.compile(r"\bfull[- ]?time\b|\bpermanent\b", re.I)
_INTERN = re.compile(r"\bintern(ship)?\b", re.I)
_TITLE_CONTRACT = re.compile(r"\bcontract(or)?\b(?!\s*(engineer|developer|manager|management|specialist|analyst|administrator|lawyer|attorney))|"
                             r"\btemp\b|contract[- ]to[- ]hire", re.I)
# description phrases strong enough to set the type when the ATS has no structured field
_DESC_CONTRACT = re.compile(r"(this is|this|is a|as a)\s+(\w+\s+){0,2}contract(or)?\s+(role|position|engagement|opportunity|assignment)|"
                            r"contract (length|duration|term)|\b\d+[- ](month|week)s? contract\b|contract[- ]to[- ]hire|\bc2c\b|corp[- ]to[- ]corp|\b1099\b", re.I)
_DESC_PART = re.compile(r"(this is|is a)\s+(\w+\s+){0,2}part[- ]time\s+(role|position|job)|\bpart[- ]time\b.{0,40}\bhours?\b", re.I)


def _contract_subtype(text):
    if _C2C.search(text):
        return "contract_c2c"
    if _1099.search(text):
        return "contract_1099"
    if _W2.search(text):
        return "contract_w2"
    return "contract"


def employment_type(structured="", title="", desc=""):
    """Work type of a posting as a config value ('full_time', 'part_time', 'contract_w2', 'contract_c2c',
    'contract_1099'), 'contract' when it is a contract of unknown kind, 'intern', or '' when nothing says.
    structured: the ATS field (Ashby employmentType 'FullTime'/'PartTime'/'Contract'/'Temporary'/'Intern',
    Lever categories.commitment, a Greenhouse 'Employment Type' metadata value)."""
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", structured or "")
    text = f"{title or ''} {desc or ''}"
    if s.strip():
        if _INTERN.search(s): return "intern"
        if _CONTRACT.search(s) or _C2C.search(s) or _1099.search(s): return _contract_subtype(s + " " + text)
        if _PART.search(s): return "part_time"
        if _FULL.search(s): return "full_time"
    t = title or ""
    if _INTERN.search(t): return "intern"
    if _TITLE_CONTRACT.search(t) or _C2C.search(t) or _1099.search(t): return _contract_subtype(text)
    if _PART.search(t): return "part_time"
    d = desc or ""
    if _DESC_CONTRACT.search(d): return _contract_subtype(d)
    if _DESC_PART.search(d): return "part_time"
    if _FULL.search(d) or _FULL.search(t): return "full_time"
    return ""


def type_decision(etype, p=None):
    """-> (keep, column L label, note for column I) for a detected employment type."""
    p = _profile(p)
    if etype == "intern":
        return False, "Not stated", "internship"
    if etype == "contract":
        return config.wants_contract(p), "Not stated", "contract; W2/C2C/1099 not stated"
    if not etype:
        return True, "Not stated", "employment type not stated"
    return config.wants(p, etype), config.employment_label(etype), ""


# --- no-sponsor list (modules.h1b only) -----------------------------------------------

_NS_CACHE = {}


def no_sponsor_path():
    return os.path.join(data_root(), "profile", "no_sponsor_companies.txt")


def load_no_sponsor(p=None):
    """Set of normalised company names, or an empty set when modules.h1b is off or the file is missing."""
    if not config.module_on(_profile(p), "h1b"):
        return set()
    path = no_sponsor_path()
    if path in _NS_CACHE:
        return _NS_CACHE[path]
    out = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                name = norm(line.split("#")[0])
                if name:
                    out.add(name)
    _NS_CACHE[path] = out
    return out


def is_no_sponsor(company, p=None):
    return bool(company) and norm(company) in load_no_sponsor(p)


# --- fetching ---------------------------------------------------------------------

def get(url):
    for i in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=20) as r:
                return r.read().decode("utf-8", "ignore")
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(15 * (i + 1))
                continue
            return ""
        except Exception:
            time.sleep(3)
    return ""


def li_detail(jid):
    """Public LinkedIn guest detail page for one job id -> dict, or None. Pace calls (8-15 s apart)."""
    h = get(f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{jid}")
    if not h:
        return None
    m = re.search(r'class="show-more-less-html__markup[^"]*"[^>]*>(.*?)</div>', h, re.S)
    desc = html.unescape(re.sub(r"<[^>]+>", " ", m.group(1))) if m else ""
    desc = re.sub(r"\s+", " ", desc).strip()
    crit = dict(re.findall(r'description__job-criteria-subheader">\s*(.*?)\s*</h3>\s*<span[^>]*>\s*(.*?)\s*</span>', h, re.S))
    app = re.search(r'num-applicants__caption[^>]*>\s*(.*?)\s*<', h, re.S)
    posted = re.search(r'posted-time-ago__text[^>]*>\s*(.*?)\s*<', h, re.S)
    comp = re.search(r'class="salary compensation__salary"[^>]*>\s*(.*?)\s*<', h, re.S)
    return {"desc": desc, "criteria": {k.strip(): html.unescape(v.strip()) for k, v in crit.items()},
            "applicants": app.group(1).strip() if app else "", "posted_ago": posted.group(1).strip() if posted else "",
            "closed": "No longer accepting applications" in h,
            "salary_detail": html.unescape(comp.group(1).strip()) if comp else ""}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Quick sponsorship checks (see module docstring).")
    ap.add_argument("--company", action="append", default=[], help="check a company against the no-sponsor list")
    ap.add_argument("--text", help="file with a posting's text: report sponsorship wording")
    a = ap.parse_args(argv)
    p = _profile()
    for c in a.company:
        if not config.module_on(p, "h1b"):
            print(f"{c}: modules.h1b is off, no-sponsor list not used")
        else:
            print(f"{c}: {'ON no-sponsor list' if is_no_sponsor(c, p) else 'not listed'}")
    if a.text:
        t = open(a.text, encoding="utf-8").read()
        b, ok = SPONSOR_BLOCK.search(t), SPONSOR_OK.search(t)
        print("block:", b.group(0) if b else "-")
        print("ok:   ", ok.group(0) if ok else "-")
    return 0


if __name__ == "__main__":
    sys.exit(main())

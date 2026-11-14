"""C2C settings, built from config/profile.json (the only place personal settings live).

    from settings import load_settings
    s = load_settings()            # dict the scraper, filters and outreach builders read

Where each value comes from (key in config/profile.json, default):

    enabled           config.module_on(p, "c2c"): any contract type in targets.employment_types
    contract_types    targets.employment_types, contract ones only (contract_1099 removed when
                      sponsorship is needed: 1099 never works on a sponsored visa)
    hourly_floor      pay.hourly_floor                        0 (no rate filter)
    years             current_role.years_experience           0
    level             current_role.level                      "senior"
    needs_sponsorship work_authorization.needs_sponsorship    False
    us_citizen        work_authorization.citizenship          True when it names the US
    days              c2c.days                                30
    remote_only       c2c.remote_only                         True
    max_years_asked   c2c.max_years_asked                     12
    min_score         c2c.min_score                           55
    skip_clearance    c2c.skip_clearance                      True
    skills.core/ai    targets.skills.core / targets.skills.ai []
    title_include     c2c.title_include                       DEFAULT_TITLE_INCLUDE
    title_exclude     c2c.title_exclude                       DEFAULT_TITLE_EXCLUDE
    queries.*         c2c.queries.dice / dice_keyword / linkedin; each empty list is generated
                      from targets.titles, targets.skills and the contract types picked
                      (visa terms only when sponsorship is needed)
    firm_boards       c2c.firm_boards_file                    modules/c2c/scraper/firm_boards.json
"""
import os
import re
import sys

_d = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(_d, "core", "config.py")) and _d != os.path.dirname(_d):
    _d = os.path.dirname(_d)
sys.path.insert(0, _d)
from core import config  # noqa: E402

# Substring matches on " <lowercased title> ". Tuned for full-stack / backend / AI contract roles;
# set c2c.title_include / c2c.title_exclude in config/profile.json to change them.
DEFAULT_TITLE_INCLUDE = [
    "full stack", "full-stack", "fullstack", "software engineer", "software developer", "web developer",
    "python", "react", "node", "javascript", "typescript", "ai engineer", "ai developer", "gen ai", "genai",
    "generative ai", "llm", "agentic", "ai software", "applied ai", "backend", "back end", "tech lead",
    "technical lead", "lead engineer", "forward deployed", "architect",
]
DEFAULT_TITLE_EXCLUDE = [
    # other stacks
    "java ", "java/", "java-", ".net", "dotnet", "c#", "angular", "salesforce", "sap ", "servicenow", "mainframe",
    "databricks", "snowflake", "embedded", "ios", "android", "react native", "rust", "golang", "go developer",
    "php", "drupal", "ruby",
    # other job families
    "qa ", "tester", "test engineer", "recruiter", "sourcer", "scientist", "devops", "sre", "network", "security",
    "scrum", "data architect", "enterprise architect", "solution architect", "solutions architect", "cloud architect",
    # level
    "director", "manager", "jr.", "junior", "entry level", "intern",
]

VISA_TERMS = re.compile(r"\bh-?1b\b|\bvisa\b|\bgc[\s-]*ead\b|\bopt\b|\bcpt\b|\bh4\b", re.I)
_US = {"united states", "united states of america", "us", "usa", "u.s.", "u.s.a.", "american", "us citizen"}


def _dedupe(items):
    out, seen = [], set()
    for x in items:
        k = x.strip().lower()
        if k and k not in seen:
            seen.add(k)
            out.append(x.strip())
    return out


def is_us_citizen(p):
    if config.needs_sponsorship(p):
        return False
    c = (config.get(p, "work_authorization.citizenship", "") or "").strip().lower()
    return c in _US


def generate_queries(titles, core, ai, needs_sponsorship, contract_types=("contract_c2c",)):
    """Search terms when c2c.queries leaves a list empty, for the contract types picked.
    Visa terms ("h1b react") only when the candidate needs sponsorship: vendors who name visas are
    the ones who take H-1B through a corp."""
    titles = [t for t in titles if t.strip()][:6]
    core = [s for s in core if s.strip()]
    terms = _dedupe(core[:4] + (["AI engineer"] if ai else []) or [t.lower() for t in titles[:3]])
    dice = _dedupe([t.lower() for t in titles]
                   + [f"{s} developer" for s in core[:4]]
                   + (["AI engineer", "generative AI", "LLM engineer"] if ai else []))
    kw, li = [], []
    if "contract_c2c" in contract_types:
        kw += [f"c2c {t}" for t in terms]
        li += [f"c2c {t}" for t in terms[:5]]
        if needs_sponsorship:
            kw += [f"h1b {t}" for t in terms[:4]]
            li.append("h1b c2c developer")
        kw.append("corp to corp developer")
        li.append("corp to corp developer")
    if "contract_w2" in contract_types:
        kw += [f"w2 contract {t}" for t in terms[:3]]
        li += [f"w2 contract {t}" for t in terms[:2]]
    if "contract_1099" in contract_types and not needs_sponsorship:
        kw += [f"1099 {t}" for t in terms[:3]]
        li += [f"1099 contract {t}" for t in terms[:2]]
    return {"dice": dice, "dice_keyword": _dedupe(kw), "linkedin": _dedupe(li)}


def from_profile(p):
    """Pure mapping profile dict -> settings dict (tests call this with a fixture)."""
    g = lambda k, d=None: config.get(p, k, d)  # noqa: E731
    sponsor = config.needs_sponsorship(p)
    core = [s.lower() for s in (g("targets.skills.core") or [])]
    ai = [s.lower() for s in (g("targets.skills.ai") or [])]
    ctypes = [t for t in config.employment_types(p) if t in config.CONTRACT_TYPES
              and not (t == "contract_1099" and sponsor)]
    gen = generate_queries(g("targets.titles") or [], core, ai, sponsor, ctypes)
    q = g("c2c.queries") or {}
    queries = {k: list(q.get(k) or []) or gen[k] for k in ("dice", "dice_keyword", "linkedin")}
    boards = g("c2c.firm_boards_file") or os.path.join("modules", "c2c", "scraper", "firm_boards.json")
    return {
        "enabled": config.module_on(p, "c2c"),
        "contract_types": ctypes,
        "hourly_floor": int(g("pay.hourly_floor", 0) or 0),
        "years": int(g("current_role.years_experience", 0) or 0),
        "level": (g("current_role.level") or "senior").lower(),
        "needs_sponsorship": sponsor,
        "us_citizen": is_us_citizen(p),
        "days": int(g("c2c.days", 30) or 30),
        "remote_only": bool(g("c2c.remote_only", True)),
        "max_years_asked": int(g("c2c.max_years_asked", 12) or 12),
        "min_score": int(g("c2c.min_score", 55) or 0),
        "skip_clearance": bool(g("c2c.skip_clearance", True)),
        "skills": {"core": core, "ai": ai},
        "title_include": [t.lower() for t in (g("c2c.title_include") or DEFAULT_TITLE_INCLUDE)],
        "title_exclude": [t.lower() for t in (g("c2c.title_exclude") or DEFAULT_TITLE_EXCLUDE)],
        "queries": queries,
        "queries_generated": [k for k in queries if not (q.get(k) or [])],
        "firm_boards": boards if os.path.isabs(boards) else config.path(boards),
    }


def load_settings(p=None):
    return from_profile(config.load() if p is None else p)


MODULE_OFF = ("The contract search is off: no contract work type is selected. To turn it on, add a contract "
              "type with /setup → update my profile (targets.employment_types: contract_c2c, contract_w2 or "
              "contract_1099), then check the \"c2c\" section: days, remote_only, max_years_asked and queries.")

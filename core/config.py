"""The one place every script gets the candidate's settings from.

Usage from any script in the kit (it finds the repo root by walking up to core/config.py):

    import os, sys
    _d = os.path.dirname(os.path.abspath(__file__))
    while not os.path.exists(os.path.join(_d, "core", "config.py")) and _d != os.path.dirname(_d):
        _d = os.path.dirname(_d)
    sys.path.insert(0, _d)
    from core import config

    p = config.load()                  # dict from config/profile.json
    config.get(p, "pay.floor", 0)      # dotted lookup with a default
    config.path("applications")        # absolute path inside the repo
    config.wants(p, "contract_c2c")    # work types from targets.employment_types

Profile location: $JOB_KIT_PROFILE if set (tests use this), else <repo>/config/profile.json.
Record scripts read and write data under $JOB_KIT_DATA if set (tests use this), else the repo root.
Standard library only, Python 3.9+.
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "config", "profile.example.json")
SCHEMA_VERSION = 1

_MISSING = object()


def profile_path():
    return os.path.expanduser(os.environ.get("JOB_KIT_PROFILE") or os.path.join(ROOT, "config", "profile.json"))


def path(*parts):
    """Absolute path inside the repo, e.g. path("applications", "_events.jsonl")."""
    return os.path.join(ROOT, *parts)


def load(required=True):
    """Return the profile dict. Exits with a clear message if it is missing and required."""
    p = profile_path()
    if not os.path.exists(p):
        if required:
            sys.exit(f"No profile at {p}. Run ./setup.sh, then /setup in Claude Code.")
        return {}
    with open(p) as f:
        data = json.load(f)
    return _merge(_example_defaults(), data)


def _example_defaults():
    try:
        with open(EXAMPLE) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return {}
    d.pop("_comment", None)
    return d


def _merge(base, over):
    """Deep-merge so a profile written by an older /setup still gets new default keys."""
    if not isinstance(base, dict) or not isinstance(over, dict):
        return over
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(base.get(k), v) if isinstance(v, dict) else v
    return out


def get(p, dotted, default=None):
    cur = p
    for key in dotted.split("."):
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            return default
    return cur


# --- identity ---------------------------------------------------------------

def full_name(p):
    return get(p, "identity.full_name", "") or "the candidate"


def first_name(p):
    return (get(p, "identity.preferred_name") or full_name(p)).split()[0]


def file_stem(p):
    """'Jane Doe' -> 'Jane_Doe', used for resume filenames sent to employers."""
    return re.sub(r"[^A-Za-z0-9]+", "_", get(p, "identity.full_name", "") or "Candidate").strip("_")


# --- tracker ----------------------------------------------------------------

def sheet_url(p, row=None):
    sid = get(p, "tracker.sheet_id", "")
    if not sid:
        return ""
    url = f"https://docs.google.com/spreadsheets/d/{sid}/edit#gid={get(p, 'tracker.gid', '0')}"
    return f"{url}&range=A{row}" if row else url


# --- modules ----------------------------------------------------------------

EMPLOYMENT_TYPES = {
    # config value: label written to tracker column L "Employment Type"
    "full_time": "Full-time",
    "part_time": "Part-time",
    "contract_w2": "Contract (W2)",
    "contract_c2c": "Contract (C2C)",
    "contract_1099": "Contract (1099)",
}
CONTRACT_TYPES = ("contract_w2", "contract_c2c", "contract_1099")
LABEL_TO_TYPE = {v.lower(): k for k, v in EMPLOYMENT_TYPES.items()}


def employment_types(p):
    """The work types the candidate wants, e.g. ['full_time', 'contract_c2c']. Default full-time only."""
    return [t for t in (get(p, "targets.employment_types") or ["full_time"]) if t in EMPLOYMENT_TYPES]


def wants(p, etype):
    return etype in employment_types(p)


def wants_contract(p):
    return any(t in CONTRACT_TYPES for t in employment_types(p))


def employment_label(etype):
    """'contract_c2c' -> 'Contract (C2C)' for the tracker; unknown -> 'Not stated'."""
    return EMPLOYMENT_TYPES.get(etype, "Not stated")


def employment_type_of(label):
    """Tracker label back to the config value ('Contract (C2C)' -> 'contract_c2c'); older 'Contract' -> 'contract'."""
    s = (label or "").strip().lower()
    return LABEL_TO_TYPE.get(s) or ("contract" if s.startswith("contract") else "")


def module_on(p, name):
    """Optional modules. The contract search (modules/c2c) is on when any contract work type is wanted."""
    if name == "c2c":
        return wants_contract(p)
    return bool(get(p, f"modules.{name}", False))


def needs_sponsorship(p):
    return bool(get(p, "work_authorization.needs_sponsorship", False))


# --- filters ----------------------------------------------------------------

def pay_floor(p):
    return int(get(p, "pay.floor", 0) or 0)


NON_US = (r"london|toronto|vancouver|montreal|canada|india|bangalore|bengaluru|berlin|munich|paris|europe|emea|apac|"
          r"\buk\b|united kingdom|mexico|brazil|singapore|australia|sydney|israel|tel aviv|poland|spain|germany|"
          r"netherlands|amsterdam|ireland|dublin|latam|japan|tokyo|korea|argentina|colombia|portugal|lisbon|chile|"
          r"costa rica|china|shanghai|beijing|philippines|manila|vietnam|ukraine|romania|serbia")


def loc_regex(p):
    """Regex for acceptable job locations. Empty match-all when relocating anywhere in the US."""
    if get(p, "locations.relocation_anywhere_us"):
        return re.compile(r"", re.I)
    pat = get(p, "locations.match_regex") or "|".join(
        re.escape(a.split(",")[0].strip().lower()) for a in get(p, "locations.onsite_hybrid_areas", []) if a.strip())
    if get(p, "locations.remote_us_ok", True):
        pat = (pat + "|" if pat else "") + r"remote|united states|\busa?\b"
    extra = os.environ.get("EXTRA_LOC_OK")  # one-off extra areas for a single run
    if extra:
        pat = (pat + "|" if pat else "") + extra
    return re.compile(pat or r"^$", re.I)


def non_us_regex():
    return re.compile(NON_US, re.I)


def title_regexes(p, default_include=r".", default_exclude=r"^$"):
    inc = get(p, "targets.title_include_regex") or default_include
    exc = get(p, "targets.title_exclude_regex") or default_exclude
    return re.compile(inc, re.I), re.compile(exc, re.I)


def resume_labels(p):
    """{label: 'path (use_for)'} for company files and pick tables."""
    return {r.get("label", ""): f"{r.get('path', '')} ({r.get('use_for', '')})" for r in get(p, "resumes", [])}


# --- job portals --------------------------------------------------------------

DEFAULT_SOURCES = ["linkedin", "handshake", "indeed", "ashby", "greenhouse", "lever"]
KNOWN_SOURCES = {
    "linkedin": "LinkedIn", "handshake": "Handshake", "indeed": "Indeed", "glassdoor": "Glassdoor",
    "ashby": "Ashby boards", "greenhouse": "Greenhouse boards", "lever": "Lever boards",
    "wellfound": "Wellfound", "dice": "Dice", "ziprecruiter": "ZipRecruiter", "builtin": "Built In",
    "yc": "Y Combinator Work at a Startup", "wttj": "Welcome to the Jungle", "usajobs": "USAJOBS",
    "weworkremotely": "We Work Remotely", "remoteok": "Remote OK", "company_pages": "Company career pages",
}
LOGIN_SOURCES = {"linkedin", "handshake", "wellfound", "yc"}


def sources(p):
    """Known portal ids to search, in priority order (see KNOWN_SOURCES)."""
    return list(get(p, "search.sources") or DEFAULT_SOURCES)


def extra_portals(p):
    """Candidate-added portals: [{name, url, search_url, login_required, notes}]."""
    return [x for x in (get(p, "search.extra_portals") or []) if isinstance(x, dict) and x.get("name")]


def search_url(portal, query):
    """Fill an extra portal's search_url template ('{query}' placeholder), else its base url."""
    from urllib.parse import quote_plus
    tpl = portal.get("search_url") or ""
    return tpl.replace("{query}", quote_plus(query)) if "{query}" in tpl else (tpl or portal.get("url", ""))


# --- common form answers --------------------------------------------------------

# Answers most application forms ask; doctor warns while any is empty. "ask" means: leave for the candidate.
COMMON_ANSWERS = [
    "eeo.gender", "eeo.hispanic_latino", "eeo.race", "eeo.veteran", "eeo.disability",
    "work_authorization.authorized_in_us", "work_authorization.needs_sponsorship",
    "screening.age_18_plus", "screening.background_check_ok", "screening.drug_test_ok",
    "screening.drivers_license", "screening.current_salary_answer", "screening.previously_employed_answer",
    "screening.relatives_at_company", "screening.cover_letter",
    "logistics.notice_period", "logistics.travel_max_percent", "logistics.how_did_you_hear_default",
    "logistics.recording_consent", "education_summary.highest_level",
]


def answer(p, dotted):
    """A form answer, or None when the candidate chose 'ask me each time' (leave the field for them)."""
    v = get(p, dotted)
    return None if isinstance(v, str) and v.strip().lower() == "ask" else v


def unanswered(p):
    """Common form questions still empty in the profile (not counting deliberate 'ask')."""
    return [k for k in COMMON_ANSWERS if get(p, k, "") in ("", None, [])]


# --- validation (used by scripts/doctor.py) -----------------------------------

REQUIRED = [
    "identity.full_name", "identity.email", "identity.city", "identity.state",
    "current_role.years_experience", "targets.titles", "resumes", "tracker.sheet_id",
]


def validate(p):
    """Return (errors, warnings) as lists of strings. Errors mean the kit can't run."""
    errors, warns = [], []
    if not p:
        return ["profile is empty"], warns
    if p.get("schema_version") != SCHEMA_VERSION:
        warns.append(f"schema_version is {p.get('schema_version')!r}, expected {SCHEMA_VERSION}")
    for key in REQUIRED:
        v = get(p, key, _MISSING)
        if v is _MISSING or v in ("", [], None):
            (warns if key == "tracker.sheet_id" else errors).append(f"{key} is empty")
    for r in get(p, "resumes", []):
        rp = r.get("path", "")
        if rp and not os.path.exists(rp if os.path.isabs(rp) else path(rp)):
            errors.append(f"resume '{r.get('label')}' not found at {rp}")
    for key in ("targets.title_include_regex", "targets.title_exclude_regex", "targets.skip_levels_regex",
                "targets.primary_stack_regex", "locations.match_regex"):
        v = get(p, key, "")
        if v:
            try:
                re.compile(v)
            except re.error as e:
                errors.append(f"{key} is not a valid regex: {e}")
    for key in ("targets.other_stack_knockouts", "targets.domain_skips"):
        for item in get(p, key, []):
            try:
                re.compile(item.get("regex", ""))
            except re.error as e:
                errors.append(f"{key} '{item.get('label')}' is not a valid regex: {e}")
    pos = get(p, "pay.position_in_posted_range", 0.75)
    if not (isinstance(pos, (int, float)) and 0 <= pos <= 1):
        errors.append("pay.position_in_posted_range must be between 0 and 1")
    bad_types = [t for t in (get(p, "targets.employment_types") or []) if t not in EMPLOYMENT_TYPES]
    if bad_types:
        errors.append(f"targets.employment_types has unknown value(s) {bad_types}; use {sorted(EMPLOYMENT_TYPES)}")
    if not employment_types(p):
        errors.append("targets.employment_types is empty")
    if needs_sponsorship(p) and wants(p, "contract_1099"):
        warns.append("contract_1099 is selected but the candidate needs sponsorship; visa holders usually can't work 1099")
    if wants_contract(p) and not get(p, "pay.hourly_floor"):
        warns.append("a contract type is selected but pay.hourly_floor is 0; contract roles won't be filtered by rate")
    unknown = [s for s in sources(p) if s not in KNOWN_SOURCES]
    if unknown:
        warns.append(f"search.sources has unknown id(s) {unknown}; add other sites to search.extra_portals instead")
    for x in get(p, "search.extra_portals") or []:
        if not (isinstance(x, dict) and x.get("name") and x.get("url")):
            errors.append(f"search.extra_portals entry needs a name and url: {x!r}")
    if "handshake" in sources(p) and get(p, "education_summary.student_status") == "graduated" \
            and not get(p, "education_summary.graduation_date"):
        warns.append("Handshake is on but education_summary.graduation_date is empty; Handshake is for students and recent grads")
    if get(p, "eeo.veteran", "").lower().startswith("i identify as one or more") and not get(p, "eeo.veteran_detail"):
        warns.append("eeo.veteran says protected veteran but eeo.veteran_detail lists no category")
    left = unanswered(p)
    if left:
        warns.append(f"{len(left)} common form question(s) unanswered, e.g. {left[0]}: run /setup → update my profile")
    if get(p, "modules.c2c") is not None:
        warns.append("modules.c2c is no longer used; add contract_c2c to targets.employment_types instead")
    if module_on(p, "h1b") and not needs_sponsorship(p):
        warns.append("modules.h1b is on but work_authorization.needs_sponsorship is false")
    if needs_sponsorship(p) and get(p, "work_authorization.any_employer_answer") == "Yes":
        warns.append("needs sponsorship but any_employer_answer is 'Yes'; most visas are employer-specific (usually 'No')")
    if not get(p, "inbox.gmail_address"):
        warns.append("inbox.gmail_address is empty; /review-emails will ask which inbox to read")
    return errors, warns

#!/usr/bin/env python3
"""Generate profile/ashby_fill.js from config/profile.json (rerun after any profile change), and print the
resolved form answers for any platform.

Usage:
  make_fill_js.py [--out PATH]      # writes profile/ashby_fill.js
  make_fill_js.py --answers         # JSON: every common form answer + the left_for_candidate list

The generated script fills Ashby application forms (identity, links, start date, how-did-you-hear, location,
education level/graduation/GPA per education_summary.share_gpa, languages, certifications, references,
portfolio, current salary per screening.current_salary_answer, and yes/no questions: authorization,
sponsorship, relocation, travel, 18+, background check, drug test, driver's license, transportation,
weekends/overtime, contract-to-hire, previously employed, relatives, remote setup, recording consent,
veteran / military spouse). It reports every field it did not fill, with the profile's EEO answer as a hint
for EEO dropdowns. It never sets the salary ask (that depends on each posting's range), never ticks consents,
never fills anything on the "never ask or store" list (SSN, date of birth, license numbers, criminal history,
bank details, attestations...) and never clicks Submit. A profile value of "ask" is never filled.
In the browser: store it once per origin with localStorage.setItem('__afill', <file text>) and run
eval(localStorage.getItem('__afill')) on each Ashby application page.
"""
import argparse, json, os, re, sys

_d = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(_d, "core", "config.py")) and _d != os.path.dirname(_d):
    _d = os.path.dirname(_d)
sys.path.insert(0, _d)
from core import config  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

# .claude/skills/setup/references/questions.md -> "Never ask or store": always left for the candidate.
NEVER = [
    "SSN or national ID number", "date of birth", "passwords", "bank or card details", "driver's license number",
    "criminal history", "health details beyond the voluntary disability form", "SMS / marketing consent",
    "legal attestations, certifications and signatures",
]
NEVER_RX = (r"social security|\bssn\b|national (id|insurance)|tax id|date of birth|\bdob\b|birth ?date|password|"
            r"bank|routing|account number|card number|licen[cs]e (number|no\b|#)|criminal|convict|felon|arrest|"
            r"\bsms\b|text messages?|marketing (emails?|communications?|messages?)|attest|i certify|signature|e-?sign")


def js_regex(pattern):
    """Python regex -> body of a JS /.../i literal (drops inline flags, escapes slashes)."""
    pattern = re.sub(r"\(\?[aiLmsux]+\)", "", pattern or "")
    return re.sub(r"(?<!\\)/", r"\/", pattern)


def yn(v):
    """Profile value -> 'Yes' / 'No', or None when it isn't a plain yes/no (e.g. 'Sometimes', 'ask', '')."""
    if isinstance(v, bool):
        return "Yes" if v else "No"
    s = str(v or "").strip().lower()
    if s.startswith("yes"):
        return "Yes"
    if s.startswith("no") and not s.startswith("non"):
        return "No"
    return None


def gpa_answer(p, required=False):
    """GPA text per education_summary.share_gpa ('share' | 'only_when_required' | 'never'), else None."""
    gpa = config.answer(p, "education_summary.gpa")
    if not gpa:
        return None
    rule = config.get(p, "education_summary.share_gpa", "only_when_required") or "only_when_required"
    if rule == "never" or (rule == "only_when_required" and not required):
        return None
    scale = config.get(p, "education_summary.gpa_scale", "") or ""
    return f"{gpa}/{scale}" if scale and "/" not in str(gpa) else str(gpa)


def _list_text(items, fmt):
    return "; ".join(fmt(x) for x in items or [] if x) if items else ""


def veteran_yn(p):
    v = (config.answer(p, "eeo.veteran") or "").lower()
    if v.startswith("i am not"):
        return "No"
    if v.startswith("i identify") or v.startswith("i am a veteran"):
        return "Yes"
    return None


# (topic, config key or None, resolver) for every common question. Resolver -> answer text, or None = leave.
def form_answers(p):
    a = lambda k: config.answer(p, k)  # noqa: E731
    langs = config.get(p, "screening.languages", []) or []
    rows = [
        ("18 or older", "screening.age_18_plus", yn(a("screening.age_18_plus"))),
        ("background check", "screening.background_check_ok", yn(a("screening.background_check_ok"))),
        ("drug test", "screening.drug_test_ok", yn(a("screening.drug_test_ok"))),
        ("driver's license (yes/no only, never the number)", "screening.drivers_license", yn(a("screening.drivers_license"))),
        ("reliable transportation", "screening.reliable_transportation", yn(a("screening.reliable_transportation"))),
        ("weekends / evenings / on-call", "screening.weekends_ok", a("screening.weekends_ok") or None),
        ("overtime", "screening.overtime_ok", a("screening.overtime_ok") or None),
        ("open to contract-to-hire", "screening.open_to_contract_to_hire", yn(a("screening.open_to_contract_to_hire"))),
        ("previously worked at / applied to this company", "screening.previously_employed_answer", a("screening.previously_employed_answer") or None),
        ("relatives or friends at the company", "screening.relatives_at_company", a("screening.relatives_at_company") or None),
        ("interview accommodations", "screening.accommodations", a("screening.accommodations") or None),
        ("remote setup", "screening.remote_setup", yn(a("screening.remote_setup"))),
        ("time-zone overlap", "screening.timezone_overlap", a("screening.timezone_overlap") or None),
        ("max days in office per week", "screening.hybrid_days_max", str(a("screening.hybrid_days_max") or "") or None),
        ("current / previous salary", "screening.current_salary_answer", a("screening.current_salary_answer") or None),
        ("cover letter rule", "screening.cover_letter", a("screening.cover_letter") or None),
        ("portfolio / work samples", "screening.portfolio_url", a("screening.portfolio_url") or a("identity.website") or None),
        ("writing sample", "screening.writing_sample", a("screening.writing_sample") or None),
        ("references", "screening.references", a("screening.references") or None),
        ("languages", "screening.languages",
         _list_text(langs, lambda x: f"{x.get('language')}" + (f" ({x['level']})" if x.get("level") else "")) or None),
        ("certifications", "screening.certifications", _list_text(config.get(p, "screening.certifications", []), str) or None),
        ("licenses", "screening.licenses", _list_text(config.get(p, "screening.licenses", []), str) or None),
        ("highest education level", "education_summary.highest_level", a("education_summary.highest_level") or None),
        ("student status", "education_summary.student_status", a("education_summary.student_status") or None),
        ("graduation date", "education_summary.graduation_date", a("education_summary.graduation_date") or None),
        ("GPA (when the field is optional)", "education_summary.share_gpa", gpa_answer(p, required=False)),
        ("GPA (when the field is required)", "education_summary.share_gpa", gpa_answer(p, required=True)),
        ("honors / coursework", "education_summary.honors", a("education_summary.honors") or None),
        ("interview recording / AI notetaker consent", "logistics.recording_consent", yn(a("logistics.recording_consent"))),
        ("non-compete", "logistics.non_compete", None),  # always the candidate's call
        ("veteran (yes/no form)", "eeo.veteran", veteran_yn(p)),
        ("protected veteran categories", "eeo.veteran_detail", _list_text(config.get(p, "eeo.veteran_detail", []), str) or None),
        ("military spouse / dependent", "eeo.military_spouse", a("eeo.military_spouse") or None),
    ]
    for k in ("gender", "hispanic_latino", "race", "veteran", "disability", "sexual_orientation", "transgender"):
        rows.append((f"EEO {k.replace('_', ' ')}", f"eeo.{k}", a(f"eeo.{k}") or None))
    return rows


def left_for_candidate(p):
    """Questions Claude never answers for this profile: the never-store list plus every unresolved answer."""
    left = list(NEVER)
    for topic, key, ans in form_answers(p):
        if ans is None and topic not in ("GPA (when the field is optional)",):
            left.append(f"{topic} ({key})")
    return left


def values(p):
    g = lambda k, d="": config.get(p, k, d)  # noqa: E731
    a = lambda k: config.answer(p, k)  # noqa: E731
    full = g("identity.full_name", "")
    first, *rest = full.split() or [""]
    loc = g("locations.location_answer", "") or ", ".join(x for x in [g("identity.city"), g("identity.state")] if x)
    ans = {t: v for t, _, v in form_answers(p)}
    return {
        "name": full, "first": g("identity.preferred_name") or first, "last": " ".join(rest),
        "email": g("identity.email"), "phone": g("identity.phone"), "linkedin": g("identity.linkedin"),
        "github": g("identity.github") or g("identity.website"), "website": g("identity.website") or g("identity.github"),
        "start": g("logistics.notice_period", "2 weeks"), "company": g("current_role.company"),
        "pronouns": g("identity.pronouns"), "pron": g("identity.name_pronunciation"),
        "source": g("logistics.how_did_you_hear_default", "LinkedIn"), "loc": loc,
        "locReloc": f"{loc} (open to relocation)" if loc and g("locations.relocation_anywhere_us") else "",
        "title": g("current_role.title"), "yrs": str(g("current_role.years_experience", "") or ""),
        "salaryNow": ans["current / previous salary"] or "",
        "references": ans["references"] or "", "portfolio": ans["portfolio / work samples"] or "",
        "writing": ans["writing sample"] or "", "languages": ans["languages"] or "",
        "certs": ans["certifications"] or "", "licenses": ans["licenses"] or "",
        "edu": ans["highest education level"] or "", "grad": ans["graduation date"] or "",
        "gpa": ans["GPA (when the field is optional)"] or "", "gpaReq": ans["GPA (when the field is required)"] or "",
        "tz": ans["time-zone overlap"] or "", "hybridDays": ans["max days in office per week"] or "",
        "eeo": {k: (a(f"eeo.{k}") or "") for k in ("gender", "hispanic_latino", "race", "veteran", "disability",
                                                    "sexual_orientation", "transgender", "military_spouse")},
        "veteranDetail": ans["protected veteran categories"] or "",
    }


def yn_rules(p):
    """[[regex, 'Yes'|'No', 'verify'?], ...] in match order. Unresolved answers get no rule (left for the candidate)."""
    a = lambda k: config.answer(p, k)  # noqa: E731
    needs = config.needs_sponsorship(p)
    auth = config.get(p, "work_authorization.authorized_in_us", True)
    any_emp = a("work_authorization.any_employer_answer")
    any_emp = yn(any_emp) if any_emp is not None and any_emp != "" else ("No" if needs else "Yes")
    rules = []
    if any_emp:
        rules.append([r"without (any )?restriction|for any employer", any_emp])
    rules += [
        [r"without (\w+[- ])?(sponsor|visa|support)|no(t)? (need|require)\w* (\w+ )?sponsor", "No" if needs else "Yes"],
        [r"sponsor|visa", "Yes" if needs else "No"],
        [r"authori[sz]ed|legally (able|eligible)|eligible to work|right to work", "Yes" if auth else "No"],
    ]
    if config.get(p, "locations.relocation_anywhere_us"):
        rules.append([r"^(?!.*assistance).*relocat", "Yes"])
    if (config.get(p, "logistics.travel_max_percent", 0) or 0) > 0:
        rules.append([r"travel", "Yes"])

    def add(rx, value, verify=False):
        v = yn(value)
        if v:
            rules.append([rx, v, "verify"] if verify or "verify" in str(value).lower() else [rx, v])

    add(r"background (check|screen|investigation)", a("screening.background_check_ok"))
    add(r"drug (test|screen)", a("screening.drug_test_ok"))
    add(r"driver'?s'? licen[cs]e|valid licen[cs]e to drive", a("screening.drivers_license"))
    add(r"reliable (transportation|means of transport)|own (car|vehicle|transportation)", a("screening.reliable_transportation"))
    add(r"weekends?|evenings?|on-?call|night shifts?", a("screening.weekends_ok"))
    add(r"overtime|extended hours", a("screening.overtime_ok"))
    add(r"contract[- ]to[- ]hire", a("screening.open_to_contract_to_hire"))
    add(r"previously (worked|been employed|applied|interviewed)|former employee|worked (here|at .*) before|ever (been )?employed by",
        a("screening.previously_employed_answer"), verify=True)
    add(r"relatives?|family members?|friends? (who )?work|know anyone (who works|at)", a("screening.relatives_at_company"), verify=True)
    rules.append([r"referr?(ed|al) by|employee referral|were you referred", "No", "verify"])
    add(r"18 (years|or older)|at least 18|legal (working )?age", a("screening.age_18_plus"))
    add(r"quiet|dedicated (work ?)?space|reliable (internet|high-speed)|home office", a("screening.remote_setup"))
    add(r"record(ed|ing)? (the |this |our )?(interview|call|conversation)|ai note-?taker|transcri", a("logistics.recording_consent"))
    add(r"accommodation", a("screening.accommodations"))
    add(r"military spouse|spouse of .*(military|service member)|military dependent", a("eeo.military_spouse"))
    if veteran_yn(p):
        rules.append([r"(are|were) you a (protected )?veteran|served in the (us |u\.s\. )?(armed forces|military)", veteran_yn(p)])
    office = r"(office|in[- ]person|on-?site|hybrid)"
    if config.get(p, "locations.relocation_anywhere_us"):
        rules.append([rf"^(?!.*({config.NON_US})).*{office}", "Yes"])
    else:
        areas = config.get(p, "locations.match_regex", "") or "|".join(
            re.escape(x.split(",")[0].strip().lower()) for x in config.get(p, "locations.onsite_hybrid_areas", []) or [] if x.strip())
        if areas:
            rules.append([rf"{office}.*({areas})|({areas}).*{office}", "Yes"])
    return rules


def render(p):
    def rule_js(r):
        extra = f", '{r[2]}'" if len(r) > 2 else ""
        return f"[/{js_regex(r[0])}/i, '{r[1]}'{extra}]"
    yn_js = "[ " + ", ".join(rule_js(r) for r in yn_rules(p)) + " ]"
    with open(os.path.join(HERE, "ashby_fill.template.js"), encoding="utf-8") as fh:
        js = fh.read()
    return (js.replace("__V__", json.dumps(values(p), ensure_ascii=False)).replace("__YN__", yn_js)
              .replace("__NEVER__", "/" + js_regex(NEVER_RX) + "/i"))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Write profile/ashby_fill.js from the profile, or print form answers.")
    ap.add_argument("--out", default=config.path("profile", "ashby_fill.js"))
    ap.add_argument("--answers", action="store_true", help="print the resolved answers and left_for_candidate as JSON")
    a = ap.parse_args(argv)
    p = config.load()
    if a.answers:
        print(json.dumps({"answers": {f"{t} [{k}]": v for t, k, v in form_answers(p) if v is not None},
                          "left_for_candidate": left_for_candidate(p)}, indent=1, ensure_ascii=False))
        return 0
    js = render(p)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        fh.write(js)
    needs = config.needs_sponsorship(p)
    print(f"wrote {a.out} ({len(js)} chars); sponsorship answers: {'needs sponsorship' if needs else 'no sponsorship needed'}; "
          f"{len(left_for_candidate(p)) - len(NEVER)} profile answers left for the candidate")
    return 0


if __name__ == "__main__":
    sys.exit(main())

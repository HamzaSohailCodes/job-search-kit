"""Decide whether a job fits, and score it (same weights as the job-match rubric).

`prof` is the settings dict from settings.load_settings() (built from config/profile.json).
Contract types use the config values from core.config: contract_c2c, contract_w2, contract_1099."""
import re
from datetime import date, timedelta

# "third party" alone is left out: postings use it for "third-party APIs" too.
C2C_YES = re.compile(r"\bc2c\b|corp[\s-]*to[\s-]*corp|corp[\s-]*corp|\b1099\s*/\s*c2c", re.I)
C2C_NO = re.compile(r"no\s*c2c|not\s+(?:open\s+to\s+)?c2c|w[\s-]?2\s*only|only\s*w[\s-]?2|w2\s*profiles|w2\s*role|no\s*corp|no\s*third[\s-]*part", re.I)
# Vendor postings that name visas ("H1B, GC, USC", "GC-EAD") almost always take outside contractors.
VISA_FRIENDLY = re.compile(r"\bh-?1b\b|\bgc[\s-]*ead\b|\bh4[\s-]*ead\b|\bany visa\b|\ball visas?\b|\btn visa\b", re.I)
W2_MENTION = re.compile(r"\bw-?2\b", re.I)
T1099_MENTION = re.compile(r"\b1099\b|independent contractor", re.I)
W2_ONLY = re.compile(r"w[\s-]?2\s*only|only\s*w[\s-]?2|w2\s*profiles|w2\s*role", re.I)
NO_W2 = re.compile(r"no\s*w-?2\b|not\s+(?:open\s+to\s+)?w-?2\b", re.I)
NO_1099 = re.compile(r"no\s*1099\b|not\s+(?:open\s+to\s+)?1099\b", re.I)
# Hourly rates: "$85/hr", "$70-90 per hour", "$80 - $95/hour", "Rate: $75 hourly".
RATE = re.compile(r"\$\s?(\d{2,3}(?:\.\d+)?)(?:\s*(?:-|–|to)\s*\$?\s?(\d{2,3}(?:\.\d+)?))?\s*"
                  r"(?:/\s*(?:hr|hour|h)\b|per\s*(?:hr|hour)\b|an\s*hour\b|hourly\b)", re.I)
C2C, W2, T1099 = "contract_c2c", "contract_w2", "contract_1099"
LABELS = {C2C: "Contract (C2C)", W2: "Contract (W2)", T1099: "Contract (1099)"}
SHORT = {C2C: "C2C", W2: "W2", T1099: "1099"}
ONSITE = re.compile(r"\b(onsite|on-site|hybrid)\b", re.I)
FULLY_REMOTE = re.compile(r"100\s*%\s*remote|fully remote|remote\s*\(us|remote[\s-]*(?:usa|us|united states)\b|location\s*:\s*remote", re.I)
REMOTE = re.compile(r"\bremote\b|\btelecommute\b|work from home|\bwfh\b", re.I)
NON_US = re.compile(r"remote[^.\n]{0,15}\b(canada|india|uk|mexico|latam|europe|philippines)\b|\b(canada|india)\s*only", re.I)
CLEARANCE = re.compile(r"\b(secret|ts/sci|top secret|public trust|clearance)\b", re.I)
VISA_ONLY = re.compile(r"\b(usc|us citizens?)\s*only\b|only\s*(usc|us citizens?)\b", re.I)
# Roles closed to candidates who need sponsorship (checked only when they do).
NO_H1B = re.compile(
    r"\b(?:usc|gc|us citizens?|green card(?: holders?)?)\s*(?:/|,|or|and|&)\s*(?:usc|gc|us citizens?|green card(?: holders?)?)"
    r"(?:\s*(?:/|,|or|and|&)\s*(?:usc|gc|gc[\s-]*ead|green card))?\s*(?:holders?\s*)?only\b"
    r"|\bno\s*h-?1b|\bnot\s*(?:open\s*to\s*|accepting\s*)?h-?1b|\bh-?1b\s*(?:not|n't)|\bno\s*(?:visa\s*)?sponsorship\b"
    r"|\bcitizens?\s*(?:and|or)\s*green card holders?\s*only|\bmust be (?:a )?(?:us citizen|usc)", re.I)


def years_asked(text):
    """Overall years asked. Postings list several ("2+ years of AI, 8+ years overall"); the
    largest one that is about experience is the real bar. Ignores "our company has 20 years"."""
    nums = []
    for m in re.finditer(r"(\d{1,2})\s*\+?\s*(?:-\s*\d{1,2}\s*)?(?:years|yrs)(?=(.{0,50}))", text, re.I):
        n = int(m.group(1))
        if 1 <= n <= 20 and re.search(r"exp|develop|engineer|hands|professional|industry|software", m.group(2), re.I):
            nums.append(n)
    return max(nums) if nums else None


def c2c_status(job):
    text = f"{job.title}\n{job.description}"
    if job.employment in ("DICE_NO_C2C", "DICE_NOT_CONTRACT"):
        return "no"
    if C2C_NO.search(text):
        return "no"
    if job.employment == "DICE_C2C":
        return "yes"
    if re.search(r"\bw-?2\b", job.title, re.I) and not re.search(r"c2c|corp", job.title, re.I):
        return "no"  # "(W2, EST candidates)" in a title means W2 only
    if job.employment == "THIRD_PARTY" or re.search(r"\bc2c\b|corp[\s-]*to[\s-]*corp|corp[\s-]*corp", text, re.I):
        return "yes"
    if C2C_YES.search(text):
        return "yes"
    if VISA_FRIENDLY.search(text):
        return "likely"
    return "unknown"


def accepted_types(job):
    """(accepted, excluded): sets of contract types the post says it takes / rules out.
    Dice badges ("Contract Corp To Corp", "Contract W2", "Contract Independent") win when present."""
    acc, exc = set(), set()
    text = f"{job.title}\n{job.description}"
    for b in (job.extra or {}).get("dice_types", []) or []:
        bl = b.lower()
        if re.search(r"corp\s*to\s*corp|third party", bl):
            acc.add(C2C)
        if re.search(r"\bw-?2\b", bl):
            acc.add(W2)
        if re.search(r"independent|1099", bl):
            acc.add(T1099)
    st = c2c_status(job)
    if st == "yes":
        acc.add(C2C)
    elif st == "no":
        exc.add(C2C)
        acc.discard(C2C)
    if W2_ONLY.search(text) or (re.search(r"\bw-?2\b", job.title, re.I) and not re.search(r"c2c|corp", job.title, re.I)):
        acc.add(W2)
        exc.update({C2C, T1099})
        acc -= {C2C, T1099}
    elif W2_MENTION.search(text) and not NO_W2.search(text):
        acc.add(W2)
    if NO_W2.search(text):
        exc.add(W2)
        acc.discard(W2)
    if T1099_MENTION.search(text) and not NO_1099.search(text) and T1099 not in exc:
        acc.add(T1099)
    if NO_1099.search(text):
        exc.add(T1099)
        acc.discard(T1099)
    if job.employment == "DICE_NO_C2C":  # badges say contract, but no Corp To Corp
        acc.discard(C2C)
        exc.add(C2C)
    return acc, exc


def employment_type(job, prof):
    """Config value for tracker column L: the first wanted type the post confirms (C2C, then W2,
    then 1099), or "" for Not stated."""
    acc, _ = accepted_types(job)
    for t in (C2C, W2, T1099):
        if t in acc and t in prof["contract_types"]:
            return t
    return ""


def hourly_rate(job):
    """(low, high) hourly rate posted, or None. Dice pay "$60-80" without a unit counts as hourly
    when both numbers are under 300."""
    m = RATE.search(f"{job.pay}\n{job.description}")
    if m:
        lo = float(m.group(1))
        return lo, float(m.group(2) or lo)
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", (job.pay or "").replace(",", ""))]
    if nums and all(5 <= n < 300 for n in nums):
        return min(nums), max(nums)
    return None


def check(job, prof):
    """Return (keep: bool, reason: str)."""
    t = job.title.lower()
    text = f"{job.title}\n{job.location}\n{job.description}"
    wanted = set(prof["contract_types"])
    if any(x in f" {t} " for x in prof["title_exclude"]):
        return False, "title outside stack/level"
    if not any(x in t for x in prof["title_include"]):
        return False, "title not a target role"
    if job.posted:
        cutoff = (date.today() - timedelta(days=prof["days"])).isoformat()
        if job.posted < cutoff:
            return False, "older than window"
    if job.employment == "DICE_NOT_CONTRACT":
        return False, "not a contract role (Dice: full/part time)"
    acc, exc = accepted_types(job)
    if acc and not acc & wanted:
        return False, "only " + "/".join(SHORT[x] for x in (C2C, W2, T1099) if x in acc) + " (type not selected)"
    if not acc and wanted <= exc:
        return False, "rules out " + "/".join(SHORT[x] for x in (C2C, W2, T1099) if x in wanted)
    if prof["remote_only"]:
        if ONSITE.search(job.title) and not REMOTE.search(job.title):
            return False, "hybrid/onsite"
        if job.remote is False:
            return False, "not remote"
        if job.remote is None and not REMOTE.search(text):
            return False, "not remote"
        if job.remote is None and ONSITE.search(text) and not FULLY_REMOTE.search(text):
            return False, "hybrid/onsite"
        if NON_US.search(text):
            return False, "remote outside US"
    if prof.get("skip_clearance", True) and CLEARANCE.search(text):
        return False, "needs clearance"
    if not prof.get("us_citizen") and VISA_ONLY.search(text):
        return False, "US citizens only"
    if prof.get("needs_sponsorship") and NO_H1B.search(text):
        return False, "closed to visa holders (GC/USC only or no sponsorship)"
    y = years_asked(job.description)
    if y and y > prof["max_years_asked"]:
        return False, f"asks {y}+ years"
    rate = hourly_rate(job)
    if prof.get("hourly_floor") and rate and rate[1] < prof["hourly_floor"]:
        return False, "rate below pay.hourly_floor"
    return True, ""


def terms_text(job, prof, etype=None):
    """Tracker column S (Rate / Terms), e.g. "$85-95/hr, C2C confirmed, remote" or "C2C not stated"."""
    etype = employment_type(job, prof) if etype is None else etype
    rate = hourly_rate(job)
    parts = []
    if rate:
        lo, hi = (int(x) if x == int(x) else x for x in rate)
        parts.append(f"${lo}/hr" if lo == hi else f"${lo}-{hi}/hr")
    if etype:
        parts.append(f"{SHORT[etype]} confirmed")
    elif C2C in prof["contract_types"] and c2c_status(job) == "likely":
        parts.append("C2C likely (names visas)")
    else:
        parts.append(("C2C" if C2C in prof["contract_types"] else "Terms") + " not stated")
    if job.remote:
        parts.append("remote")
    return ", ".join(parts)


def score(job, prof):
    """Score 0-100: skills 35, experience 25, seniority 15, domain 10, logistics 15."""
    text = f"{job.title} {job.description}".lower()
    core = [k for k in prof["skills"]["core"] if re.search(r"\b" + re.escape(k) + r"\b", text)]
    ai = [k for k in prof["skills"]["ai"] if re.search(r"\b" + re.escape(k) + r"\b", text)]
    skills = min(100, 40 + 8 * len(set(core)) + 6 * len(set(ai)))

    y = years_asked(job.description)
    gap = (y or prof["years"]) - prof["years"]
    experience = 100 if gap <= 0 else max(20, 100 - 18 * gap)

    t = job.title.lower()
    senior_title = re.search(r"\b(lead|staff|sr\.?|senior|architect|principal)\b", t)
    mid_title = re.search(r"\b(mid|ii|intermediate)\b", t)
    if prof.get("level") == "senior":
        seniority = 100 if senior_title else 65 if mid_title else 80
    else:
        seniority = 100 if mid_title else 60 if senior_title else 90

    domain = 80 if ai or "full stack" in text or "full-stack" in text else 65

    c2c = c2c_status(job)
    etype = employment_type(job, prof)
    if etype:
        logistics = 100  # a wanted contract type is confirmed
    elif C2C in prof["contract_types"] and c2c == "likely":
        logistics = 85
    else:
        logistics = 65
    if job.remote is None:
        logistics -= 10

    total = 0.35 * skills + 0.25 * experience + 0.15 * seniority + 0.10 * domain + 0.15 * logistics
    return round(total), {"c2c": c2c, "employment_type": etype, "terms": terms_text(job, prof, etype),
                          "years_asked": y or "", "skills_hit": ", ".join(sorted(set(core + ai)))}

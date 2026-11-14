"""Dice: remote 'Third Party' jobs (Dice's tag for roles that accept C2C)."""
import re
import urllib.parse

from common import Job, fetch, html_to_text, ld_jobposting


def search_ids(query, pages=3, posted="SEVEN", emp="THIRD_PARTY"):
    ids = []
    for page in range(1, pages + 1):
        params = {
            "q": query,
            "filters.employmentType": emp,
            "filters.workplaceTypes": "Remote",
            "page": page,
        }
        if posted:
            params["filters.postedDate"] = posted
        html = fetch("https://www.dice.com/jobs?" + urllib.parse.urlencode(params))
        found = re.findall(r"job-detail/([0-9a-f-]{36})", html)
        new = [i for i in dict.fromkeys(found) if i not in ids]
        if not new:
            break
        ids.extend(new)
    return ids


def dice_types(html):
    """Employment badges Dice shows at the top of the job page, e.g.
    ["Contract Corp To Corp", "Contract W2", "Full Time"]. Read from the server-rendered badge row,
    not the whole page: "similar jobs" further down carry their own types."""
    i = html.find("order-4 flex w-full flex-wrap gap-3")
    if i < 0:
        return []
    seg = html[i:i + 4000]
    badges = re.findall(r'leading-none">([^<]+)</div>', seg)
    return [b.strip() for b in badges if re.match(r"(Contract|Full[ -]?Time|Part[ -]?Time|Third Party)", b.strip(), re.I)]


def classify(types, emp):
    """DICE_C2C: lists Contract Corp To Corp. DICE_NO_C2C: contract, but only W2 / Independent (1099).
    DICE_NOT_CONTRACT: only full-time / part-time. Falls back to the search filter when no badges are found."""
    if not types:
        return emp
    if any(re.search(r"corp\s*to\s*corp", t, re.I) for t in types):
        return "DICE_C2C"
    if any(t.lower().startswith("contract") for t in types):
        return "DICE_NO_C2C"
    return "DICE_NOT_CONTRACT"


def job_detail(job_id, emp="THIRD_PARTY"):
    url = f"https://www.dice.com/job-detail/{job_id}"
    html = fetch(url)
    ld = ld_jobposting(html)
    if not ld:
        return None
    types = dice_types(html)
    pay = ""
    sal = ld.get("baseSalary")
    if isinstance(sal, dict):
        v = sal.get("value")
        if isinstance(v, dict) and v.get("minValue"):
            pay = f"${v.get('minValue')}-{v.get('maxValue')}"
        elif isinstance(v, str):
            pay = v
    return Job(
        source="dice",
        title=ld.get("title", ""),
        company=(ld.get("hiringOrganization") or {}).get("name", ""),
        url=url,
        posted=(ld.get("datePosted") or "")[:10],
        location="Remote" if ld.get("jobLocationType") == "TELECOMMUTE" else "",
        remote=ld.get("jobLocationType") == "TELECOMMUTE",
        employment=classify(types, emp),  # DICE_C2C / DICE_NO_C2C / DICE_NOT_CONTRACT, else the search filter
        pay=pay,
        description=html_to_text(ld.get("description", "")),
        extra={"dice_types": types},
    )


def collect(queries, pages=3, days=7, log=print, keyword_queries=(), seen=None, emp="THIRD_PARTY"):
    """queries: searched among Third Party jobs (emp="CONTRACTS" searches all contract jobs, for candidates
    who did not pick C2C). keyword_queries ("c2c python", "w2 contract react"): searched among all contract
    jobs, since Dice matches the words in the posting text."""
    posted = "ONE" if days <= 1 else "THREE" if days <= 3 else "SEVEN" if days <= 7 else None
    seen = set() if seen is None else seen
    jobs = []
    plan = [(q, emp) for q in queries] + [(q, "CONTRACTS") for q in keyword_queries]
    for q, emp in plan:
        ids = [i for i in search_ids(q, pages, posted, emp) if i not in seen]
        seen.update(ids)
        log(f"  dice [{emp.lower()}] '{q}': {len(ids)} new")
        for i in ids:
            j = job_detail(i, emp)
            if j:
                jobs.append(j)
    return jobs

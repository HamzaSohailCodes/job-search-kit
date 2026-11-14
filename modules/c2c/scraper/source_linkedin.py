"""LinkedIn public (logged-out) job search: remote, contract, last N days.

LinkedIn rate-limits quickly, so this goes slowly (several seconds between calls) and stops
early when it is told to back off. Expect a few dozen jobs per run, not hundreds."""
import re
import time
import urllib.parse

import common
from common import Job, html_to_text

BASE = "https://www.linkedin.com/jobs-guest/jobs/api"
LI_DELAY = 4.0


def _get(url):
    old = common.DELAY
    common.DELAY = LI_DELAY
    try:
        return common.fetch(url)
    finally:
        common.DELAY = old


def search(query, days=30, pages=2):
    found = []
    for start in range(0, 25 * pages, 25):
        params = {"keywords": query, "location": "United States", "f_WT": "2", "f_JT": "C",
                  "f_TPR": f"r{days * 86400}", "start": start}
        html = _get(f"{BASE}/seeMoreJobPostings/search?" + urllib.parse.urlencode(params))
        if not html:
            break  # rate-limited or empty
        cards = re.findall(r"<li>(.*?)</li>", html, re.S)
        for c in cards:
            m = re.search(r'href="(https://[^"]*/jobs/view/[^"?]*?-?(\d{8,}))', c)
            if not m:
                continue
            found.append({
                "id": m.group(2), "url": m.group(1),
                "title": html_to_text((re.search(r'base-search-card__title">(.*?)<', c, re.S) or [None, ""])[1]),
                "company": html_to_text((re.search(r'base-search-card__subtitle">(.*?)</h4>', c, re.S) or [None, ""])[1]),
                "posted": (re.search(r'datetime="([\d-]+)"', c) or [None, ""])[1],
            })
        if len(cards) < 25:
            break
    return found


def detail(card):
    html = _get(f"{BASE}/jobPosting/{card['id']}")
    if not html:
        return None
    desc = (re.search(r'show-more-less-html__markup[^>]*>(.*?)</div>', html, re.S)
            or re.search(r'description__text--rich[^>]*>(.*?)(?:description__job-criteria|</section>)', html, re.S))
    loc = re.search(r'topcard__flavor--bullet">(.*?)<', html, re.S)
    return Job(source="linkedin", title=card["title"], company=card["company"], url=card["url"],
               posted=card["posted"], location=html_to_text(loc.group(1)) if loc else "",
               remote=None,  # searched with the remote filter, but checked against the text too
               employment="CONTRACT", description=html_to_text(desc.group(1)) if desc else "")


def collect(queries, days=30, prefilter=None, log=print):
    """prefilter(title) -> bool skips detail calls for titles that would be dropped anyway."""
    cards, seen = [], set()
    for q in queries:
        got = [c for c in search(q, days) if c["id"] not in seen]
        seen.update(c["id"] for c in got)
        log(f"  linkedin '{q}': {len(got)} new")
        cards += got
        if not got:
            time.sleep(20)  # likely rate-limited; give it a moment
    if prefilter:
        cards = [c for c in cards if prefilter(c["title"])]
    # Job pages are often refused to scripts. On the first refusal, stop asking and keep the
    # rest as leads from the search card alone (searched with the remote filter; C2C unknown).
    jobs, blocked = [], False
    for c in cards:
        j = None if blocked else detail(c)
        if j is None and not blocked:
            blocked = True
            log("  linkedin: job pages refused; keeping the rest as search-card leads")
        if j is None:
            j = Job(source="linkedin (card only)", title=c["title"], company=c["company"], url=c["url"],
                    posted=c["posted"], remote=True, employment="CONTRACT", description="")
        jobs.append(j)
    log(f"  linkedin: {len(jobs)} postings")
    return jobs

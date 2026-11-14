"""For each firm's job listing page: how many job links can a plain script see, and do the
job pages carry schema.org JobPosting data? Tells us which firms the generic reader can cover.

Usage: python3 modules/c2c/scraper/probe_boards.py   (one-off survey; edit BOARDS to probe other firms)"""
import concurrent.futures as cf
import os
import re
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import fetch, ld_jobposting  # noqa: E402

BOARDS = {
    "Lorven Technologies": "https://lorventech.com/external-jobs/",
    "DivIHN Integration": "https://www.divihn.com/careers/consultant-careers/open-jobs",
    "Sysmind": "https://www.sysmind.com/current-openings",
    "Talent Groups": "https://www.talentgroups.com/jobs",
    "Mindlance": "https://mindlance.com/job-board/",
    "Mastech Digital": "https://jobs.mastech.com/",
    "Matlen Silver": "https://matlensilver.com/jobs/",
    "Eliassen Group": "https://careers.eliassen.com/",
    "DeWinter Group": "https://www.dewintergroup.com/job-search",
    "Genesis10": "https://www.genesis10.com/find-a-job",
    "Brooksource": "https://jobs.brooksource.com/jobs/",
    "Yoh": "https://jobs.yoh.com/",
    "Beacon Hill": "https://bhsg.com/jobs/",
    "Insight Global": "https://careers-insightglobal.icims.com/jobs/search?ss=1&searchKeyword=python&in_iframe=1",
    "Judge Group": "https://careers-judge.icims.com/jobs/search?ss=1&searchKeyword=python&in_iframe=1",
    "Randstad": "https://www.randstadusa.com/jobs/remote/",
    "TEKsystems": "https://careers.teksystems.com/us/en/search-results?keywords=python",
    "Apex Systems": "https://www.apexsystems.com/job-search",
    "INSPYR Solutions": "https://www.inspyrsolutions.com/job-search/",
    "Collabera": "https://collabera.com/job-search/",
    "US Tech Solutions": "https://ustechsolutions.com/jobs-at-ustech-solutions/",
    "Swoon": "https://www.swoonstaffing.com/jobs/",
    "Pyramid Consulting": "https://jobs.sprockets.ai/en-US/pyramidinc/jobs",
    "Tanisha Systems": "https://www.tanishasystems.com/currentopenings.html",
    "Kforce": "https://www.kforce.com/find-work/search-jobs/",
    "Robert Half": "https://www.roberthalf.com/us/en/jobs/all/python",
    "Motion Recruitment": "https://motionrecruitment.com/tech-jobs",
    "Jobot": "https://jobot.com/search?q=python",
    "Experis": "https://www.experis.com/en/search?k=python",
    "Accion Labs": "https://www.accionlabs.com/careers",
    "Chabez Tech": "https://chabeztech.com/careers/",
    "Intellisoft Technologies": "https://www.intellisofttech.com/careers",
    "Amtex Systems": "https://www.amtexsystems.com/careers",
    "Burgeon IT Services": "https://www.burgeonits.com/us-openings/index.html",
}
JOBLINK = re.compile(r"/(job|jobs|job-detail|jobdetail|job-details|position|opening|careers?)/[^\"'#?\s]*[0-9a-z-]{6,}", re.I)


def links(base, html):
    out = []
    for h in re.findall(r'href=["\']([^"\']+)["\']', html):
        u = urllib.parse.urljoin(base, h).split("#")[0]
        if JOBLINK.search(urllib.parse.urlparse(u).path) and u.rstrip("/") != base.rstrip("/"):
            out.append(u)
    return list(dict.fromkeys(out))


def probe(item):
    name, url = item
    html = fetch(url)
    if not html:
        return f"{name:24} NO RESPONSE"
    ls = links(url, html)
    ld_hits = sum(1 for u in ls[:3] if ld_jobposting(fetch(u)))
    rss = re.search(r'type="application/rss\+xml"[^>]*href="([^"]+)"', html)
    js = "JS-app" if len(html) < 30000 and not ls else ""
    return f"{name:24} {len(html)//1000:4d}KB links={len(ls):3d} jsonld={ld_hits}/3 {js} {ls[:2]} {('rss ' + rss.group(1)) if rss else ''}"


if __name__ == "__main__":
    with cf.ThreadPoolExecutor(10) as ex:
        for row in ex.map(probe, BOARDS.items()):
            print(row[:300], flush=True)

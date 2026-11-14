"""Check each staffing firm's website and report which job-board platform it uses.

Usage: python3 modules/c2c/scraper/detect_platforms.py modules/c2c/scraper/firms.txt > platforms.txt
"""
import concurrent.futures as cf
import re
import sys
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
SIGS = {
    "ceipal": r"ceipal", "jobdiva": r"jobdiva",
    "bullhorn": r"bullhorn|public-rest\d*\.bullhornstaffing", "greenhouse": r"greenhouse\.io",
    "lever": r"jobs\.lever\.co", "ashby": r"ashbyhq", "workday": r"myworkdayjobs",
    "icims": r"icims\.com", "smartrecruiters": r"smartrecruiters", "jazzhr": r"applytojob\.com|jazzhr",
    "zoho": r"zohorecruit|recruit\.zoho", "breezy": r"breezy\.hr", "workable": r"workable\.com",
    "recruitee": r"recruitee", "avionte": r"avionte", "jobvite": r"jobvite",
    "paylocity": r"paylocity", "adp": r"workforcenow\.adp", "crelate": r"crelate",
    "oorwin": r"oorwin", "manatal": r"manatal", "jobadder": r"jobadder",
}
PATHS = ["", "/careers", "/jobs", "/job-openings", "/current-openings", "/find-jobs"]


def get(url):
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=12)
        return r.status, r.read(400000).decode("utf-8", "ignore")
    except Exception:
        return None, ""


def probe(line):
    name, dom, tier = [x.strip() for x in line.split("|")]
    found, links, up = {}, set(), False
    for p in PATHS:
        status, html = get(f"https://www.{dom}{p}")
        up = up or bool(status)
        for key, rx in SIGS.items():
            m = re.search(r"[^\"'\s<>]*(?:%s)[^\"'\s<>]*" % rx, html, re.I)
            if m and key not in found:
                found[key] = m.group(0)[:140]
        for link in re.findall(r'href="([^"]*(?:career|job|opening)[^"]*)"', html, re.I)[:5]:
            links.add(link[:90])
    return f"{name} | {dom} | {tier} | {'UP' if up else 'DOWN'} | {found or '-'} | {sorted(links)[:4]}"


if __name__ == "__main__":
    lines = [l for l in open(sys.argv[1]) if l.strip() and not l.startswith("#")]
    with cf.ThreadPoolExecutor(12) as ex:
        for row in ex.map(probe, lines):
            print(row)

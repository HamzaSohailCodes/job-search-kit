"""Staffing-firm career sites listed in firm_boards.json."""
import email.utils
import json
import re
import urllib.parse

from common import Job, fetch, html_to_text, ld_jobposting


def _tag(item, name):
    m = re.search(rf"<{name}[^>]*>(.*?)</{name}>", item, re.S)
    if not m:
        return ""
    return re.sub(r"^<!\[CDATA\[|\]\]>$", "", m.group(1).strip())


def wp_feed(board, queries, pages=2):
    jobs = {}
    for q in queries:
        for p in range(1, pages + 1):
            xml = fetch(f"{board['url']}?s={urllib.parse.quote(q)}&paged={p}")
            items = re.findall(r"<item>(.*?)</item>", xml, re.S)
            for it in items:
                link = _tag(it, "link")
                if link in jobs:
                    continue
                try:
                    posted = email.utils.parsedate_to_datetime(_tag(it, "pubDate")).date().isoformat()
                except Exception:
                    posted = ""
                body = _tag(it, "content:encoded") or _tag(it, "description")
                jobs[link] = Job(source=f"firm:{board['firm']}", title=html_to_text(_tag(it, "title")),
                                 company=board["firm"], url=link, posted=posted,
                                 description=html_to_text(body), tier=board["tier"])
            if len(items) < 10:
                break
    return list(jobs.values())


def _location(ld):
    locs = ld.get("jobLocation") or []
    locs = locs if isinstance(locs, list) else [locs]
    parts = []
    for l in locs:
        a = (l or {}).get("address") or {}
        if isinstance(a, dict):
            parts.append(", ".join(x for x in [a.get("addressLocality"), a.get("addressRegion")] if x))
    return "; ".join(p for p in parts if p)


def jsonld_list(board, queries, max_jobs=60):
    links = []
    for q in queries:
        url = board["url"].format(q=urllib.parse.quote(q))
        html = fetch(url)
        for h in re.findall(r'href=["\']([^"\']+)["\']', html):
            u = urllib.parse.urljoin(url, h).split("#")[0]
            if board["link_pattern"] in u and u not in links and u.rstrip("/") != url.split("?")[0].rstrip("/"):
                links.append(u)
    jobs = []
    for u in links[:max_jobs]:
        ld = ld_jobposting(fetch(u))
        if not ld:
            continue
        jobs.append(Job(source=f"firm:{board['firm']}", title=ld.get("title", ""), company=board["firm"], url=u,
                        posted=(ld.get("datePosted") or "")[:10], location=_location(ld),
                        remote=True if ld.get("jobLocationType") == "TELECOMMUTE" else None,
                        employment=json.dumps(ld.get("employmentType", "")),
                        description=html_to_text(ld.get("description", "")), tier=board["tier"]))
    return jobs


def collect(config_path, log=print):
    cfg = json.load(open(config_path))
    out = []
    for b in cfg["boards"]:
        fn = {"wp_feed": wp_feed, "jsonld_list": jsonld_list}[b["type"]]
        try:
            got = fn(b, cfg["queries"])
        except Exception as e:  # one broken site should not stop the run
            log(f"  {b['firm']}: failed ({e})")
            continue
        log(f"  {b['firm']}: {len(got)} jobs")
        out += got
    return out

"""Shared helpers: polite HTTP, HTML-to-text, and the Job record."""
import html as htmllib
import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"
DELAY = 1.0  # seconds between requests to the same host
_last_hit = {}


def fetch(url, data=None, headers=None, timeout=20):
    """GET (or POST when data is given). Waits DELAY between calls to one host. Returns text or ''."""
    host = urllib.parse.urlparse(url).netloc
    wait = DELAY - (time.time() - _last_hit.get(host, 0))
    if wait > 0:
        time.sleep(wait)
    _last_hit[host] = time.time()
    h = {"User-Agent": UA, "Accept": "*/*"}
    h.update(headers or {})
    body = None
    if data is not None:
        body = json.dumps(data).encode() if isinstance(data, (dict, list)) else data
        h.setdefault("Content-Type", "application/json")
    try:
        req = urllib.request.Request(url, data=body, headers=h)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "ignore")
    except Exception:
        return ""


def fetch_json(url, **kw):
    txt = fetch(url, **kw)
    try:
        return json.loads(txt)
    except Exception:
        return None


def html_to_text(s):
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s or "", flags=re.S | re.I)
    s = re.sub(r"<br\s*/?>|</p>|</li>|</div>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"[ \t\r\f\v]+", " ", htmllib.unescape(s)).strip()


def ld_jobposting(html):
    """Return the schema.org JobPosting dict embedded in a page, if any."""
    for m in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            j = json.loads(m.strip())
        except Exception:
            continue
        for item in j if isinstance(j, list) else j.get("@graph", [j]):
            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                return item
    return None


@dataclass
class Job:
    source: str          # e.g. "dice", "firm:VDart"
    title: str
    company: str
    url: str
    posted: str = ""     # ISO date (YYYY-MM-DD) when known
    location: str = ""
    remote: Optional[bool] = None
    employment: str = ""  # raw employment type text from the source
    pay: str = ""
    description: str = ""
    tier: str = ""       # vendor / big / ""
    extra: dict = field(default_factory=dict)

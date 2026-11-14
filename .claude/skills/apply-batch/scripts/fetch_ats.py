#!/usr/bin/env python3
"""Fetch every posting from the public Ashby, Greenhouse and Lever job-board APIs.

Usage: fetch_ats.py --run-dir batches/YYYY-MM-DD [--sources ashby,greenhouse,lever]

Slug lists live in slugs/<source>.txt next to this script (one slug per line; add new
companies there). Writes <run-dir>/{ashby,gh,lever}_boards.json as {slug: [jobs]}.
Never searches LinkedIn or Indeed.
"""
import argparse, json, os, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
UA = {"User-Agent": "Mozilla/5.0"}

SOURCES = {
    # name: (slug file, output file, url template, extract(json) -> list|None)
    "ashby": ("ashby.txt", "ashby_boards.json",
              "https://api.ashbyhq.com/posting-api/job-board/{}?includeCompensation=true",
              lambda d: d.get("jobs") if isinstance(d, dict) else None),
    "greenhouse": ("greenhouse.txt", "gh_boards.json",
                   "https://boards-api.greenhouse.io/v1/boards/{}/jobs?content=true",
                   lambda d: d.get("jobs") if isinstance(d, dict) else None),
    "lever": ("lever.txt", "lever_boards.json",
              "https://api.lever.co/v0/postings/{}?mode=json",
              lambda d: d if isinstance(d, list) and d else None),
}


def slugs(fname):
    lines = open(os.path.join(HERE, "slugs", fname)).read().split()
    return sorted({s.strip() for s in lines if s.strip() and not s.startswith("#")})


def fetch(name, run_dir):
    sfile, ofile, url, extract = SOURCES[name]
    ss = slugs(sfile)

    def get(s):
        # Greenhouse content=true payloads are large and time out under load: retry with backoff.
        # A 404 means the slug has no board on this ATS, so don't retry it.
        for i in range(3):
            try:
                req = urllib.request.Request(url.format(s), headers=UA)
                with urllib.request.urlopen(req, timeout=60) as r:
                    return s, extract(json.loads(r.read()))
            except urllib.error.HTTPError as e:
                if e.code == 404: return s, None
            except Exception:
                pass
            time.sleep(3 * (i + 1))
        return s, "failed"

    boards, failed = {}, []
    with ThreadPoolExecutor(8) as ex:
        for s, jobs in ex.map(get, ss):
            if jobs == "failed": failed.append(s)
            elif jobs is not None: boards[s] = jobs
    json.dump(boards, open(os.path.join(run_dir, ofile), "w"))
    print(f"{name}: probed {len(ss)} boards {len(boards)} jobs {sum(len(v) for v in boards.values())}"
          + (f" | FAILED after retries: {' '.join(failed)}" if failed else ""), flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--sources", default="ashby,greenhouse,lever")
    a = ap.parse_args()
    run_dir = os.path.expanduser(a.run_dir)
    os.makedirs(run_dir, exist_ok=True)
    names = [s.strip() for s in a.sources.split(",") if s.strip()]
    with ThreadPoolExecutor(len(names)) as ex:
        list(ex.map(lambda n: fetch(n, run_dir), names))

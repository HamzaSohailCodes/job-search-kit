#!/usr/bin/env python3
"""Final duplicate check before any rows are written to the tracker. Required before every paste.

Usage: check_dupes.py --rows rows.json --tracker tracker.csv [--rows-done other_rows.json ...]

rows.json: build_rows.py output (lists: A title, B company, C location, D link, ...).
tracker.csv: full export of the tracker tab (A..AC; older exports that stop at F, Q or R work too). Every work type
is compared: a role already in the tab as Contract (C2C) or Part-time is a duplicate of the same full-time role.
Exit 1 and list every row that matches an existing tracker row (or a row in --rows-done) by:
  * same URL (query strings and tracking dropped; job ids compared across URL forms), or
  * same company (normalised) and the same normalised title, or title word overlap >= 0.5 (hyphens, levels like Sr/Senior, city words ignored), or
  * WARN (exit 0): same company already Applied / Interviewing / Rejected / Offer and a title sharing 2+ core
    role words. Decide those by hand; don't add them blindly.
Run it on EVERY candidate set (ATS filter output, LinkedIn, Indeed, boards), not only the ATS one.
"""
import argparse, csv, json, os, re, sys

_d = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(_d, "core", "config.py")) and _d != os.path.dirname(_d):
    _d = os.path.dirname(_d)
sys.path.insert(0, _d)
from core import config  # noqa: E402

csv.field_size_limit(10 ** 8)
STOP = {'senior', 'sr', 'jr', 'junior', 'lead', 'staff', 'principal', 'engineer', 'engineering', 'software', 'the',
        'a', 'an', 'of', 'and', 'ii', 'iii', 'i', 'remote', 'us', 'usa', 'hybrid', 'onsite', 'on', 'site'}
ACTIVE = ('Applied', 'Interviewing', 'Rejected', 'Offer')


def norm(s):
    s = re.sub(r'\b(inc|llc|ltd|corp|corporation|co|the)\b\.?', '', (s or '').lower())
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()


def stop_words(p=None):
    """STOP plus the words of the candidate's own city names, which often get appended to titles."""
    p = p if p is not None else (config.load(required=False) or {})
    extra = set()
    for area in config.get(p, 'locations.onsite_hybrid_areas', []) or []:
        extra |= set(norm(area).split())
    return STOP | extra


def words(t, stop=STOP):
    return {w for w in norm(t).split() if w not in stop}


def url_key(u):
    u = (u or '').lower()
    m = (re.search(r'(?:jk|gh_jid|currentjobid|token)=([0-9a-z]+)', u) or re.search(r'(\d{8,})', u.split('?')[0])
         or re.search(r'([0-9a-f]{8}-[0-9a-f-]{27})', u))
    return m[1] if m else u.split('?')[0].rstrip('/')


def check(rows, existing, stop=STOP):
    """rows: [[title, company, loc, link, ...]]; existing: [(title, company, link, status)] -> (bad, warn)."""
    bad, warn = [], []
    for i, r in enumerate(rows, 1):
        t, co, u = r[0], norm(r[1]), url_key(r[3])
        w = words(r[0], stop)
        for et, eco, eu, est in existing:
            ecn = norm(eco)
            if u and u == url_key(eu):
                bad.append((i, r[1], t, f'same URL as "{et}" ({est})'))
                break
            if not (co == ecn or (co and ecn and (co in ecn or ecn in co) and min(len(co), len(ecn)) > 3)):
                continue
            ew = words(et, stop)
            if norm(t) == norm(et):  # titles made only of level/stop words ("Senior Software Engineer")
                bad.append((i, r[1], t, f'{est}: same title "{et}"'))
                break
            if w and ew:
                j = len(w & ew) / len(w | ew)
                if j >= 0.5:
                    bad.append((i, r[1], t, f'{est}: "{et}" (overlap {j:.2f})'))
                    break
                if est.split(',')[0] in ACTIVE and len(w & ew) >= 2:
                    warn.append((i, r[1], t, f'same company already {est} for "{et}"'))
                    break
    return bad, warn


def load_tracker(path):
    """[(title, company, link, 'status' or 'status, type')] from a tracker export, by header when present."""
    rows = list(csv.reader(open(path, encoding='utf-8')))
    if not rows:
        return []
    hdr = [h.strip().lower() for h in rows[0]]
    col = lambda name, default: hdr.index(name) if name in hdr else default  # noqa: E731
    ti, co, li, st, ty = col('job title', 0), col('company', 1), col('job link', 3), col('apply status', 5), col('employment type', 11)
    out = []
    for r in rows[1:]:
        if len(r) <= max(ti, co, li):
            continue
        status = r[st] if len(r) > st else ''
        etype = r[ty].strip() if len(r) > ty else ''
        out.append((r[ti], r[co], r[li], status + (f', {etype}' if etype and etype.lower() not in ('full-time', 'not stated') else '')))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description='Duplicate gate before writing rows to the tracker.')
    ap.add_argument('--rows', required=True)
    ap.add_argument('--tracker', required=True)
    ap.add_argument('--rows-done', action='append', default=[], help='rows.json already written after the export')
    a = ap.parse_args(argv)
    existing = load_tracker(a.tracker)
    for p in a.rows_done:
        for r in json.load(open(p)):
            existing.append((r[0], r[1], r[3], (r[5] if len(r) > 5 else '') +
                             (f', {r[11]}' if len(r) > 11 and r[11] and r[11].lower() not in ('full-time', 'not stated') else '')))
    rows = json.load(open(a.rows))
    bad, warn = check(rows, existing, stop_words())
    seen = {}
    for i, r in enumerate(rows, 1):  # duplicates inside the batch itself
        k = (norm(r[1]), url_key(r[3]))
        if k in seen:
            bad.append((i, r[1], r[0], f'same as row {seen[k]} of this batch'))
        seen.setdefault(k, i)
    for b in bad:
        print('DUP row', *b)
    for b in warn:
        print('WARN row', *b)
    print(f'{len(rows)} rows, {len(bad)} duplicates, {len(warn)} warnings')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())

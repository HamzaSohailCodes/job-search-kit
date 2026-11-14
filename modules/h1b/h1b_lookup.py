#!/usr/bin/env python3
"""H-1B filing history for an employer, from the public LCA disclosure data as indexed by h1bdata.info.

Optional module: used only when modules.h1b is true in config/profile.json (callers check that).

Usage:
  python3 modules/h1b/h1b_lookup.py "Acme" "Globex" ...      # one line per company
  python3 modules/h1b/h1b_lookup.py --json "Acme"            # JSON
  python3 modules/h1b/h1b_lookup.py --force "Acme"           # ignore the cache
In code:
  from h1b_lookup import lookup, evidence
  lookup("Acme") -> dict(count_recent, count_all, employers, median_wage, years, verdict)
  evidence(result) -> one-line text for the tracker's "H-1B Evidence" column (Q)

verdict: "sponsors" (5+ filings since RECENT_FROM), "some" (1-4), "none" (no filings found),
"unknown" (lookup failed, or the name is ambiguous). Evidence only: never drop a job on this alone.
A young startup with "none" may still sponsor. Cache: batches/h1b_cache.json (30 days), or $H1B_CACHE.
"""
import datetime, html, json, os, re, statistics, sys, time, urllib.parse, urllib.request

_d = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(_d, "core", "config.py")) and _d != os.path.dirname(_d):
    _d = os.path.dirname(_d)
sys.path.insert(0, _d)
from core import config  # noqa: E402

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36'
RECENT_FROM = int(os.environ.get('H1B_RECENT_FROM') or datetime.date.today().year - 2)
CACHE_DAYS = 30
_SUFFIX_WORDS = {'opco', 'lp', 'lc', 'group', 'holdings', 'holding', 'systems', 'america', 'americas', 'us', 'usa',
                 'software', 'services', 'platforms', 'international', 'global', 'north', 'labs', 'ai', 'technologies', 'inc', 'llc'}


def cache_path():
    root = os.environ.get('JOB_KIT_DATA') or config.ROOT
    return os.path.expanduser(os.environ.get('H1B_CACHE') or os.path.join(root, 'batches', 'h1b_cache.json'))


def _norm(s):
    s = re.sub(r'\b(inc|llc|ltd|corp|corporation|co|technologies|technology|labs|ai)\b\.?', '', (s or '').lower())
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()


def _fetch(q):
    u = 'https://h1bdata.info/index.php?em=' + urllib.parse.quote(q) + '&job=&city=&year=all'
    r = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': UA}), timeout=25)
    return r.read().decode('utf8', 'ignore')


def _parse(page):
    rows = []
    for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', page, re.S):
        cells = [html.unescape(re.sub(r'<[^>]+>', '', c)).strip() for c in re.findall(r'<td[^>]*>(.*?)</td>', tr, re.S)]
        if len(cells) < 6:
            continue
        emp, title, wage, loc, submit, start = cells[:6]
        status = cells[6] if len(cells) > 6 else ''
        m = re.search(r'(\d{4})', submit)
        w = re.sub(r'[^\d]', '', wage)
        rows.append({'employer': emp, 'title': title, 'wage': int(w) if w else None, 'location': loc,
                     'year': int(m[1]) if m else None, 'status': status})
    return rows


def _rows_for(company):
    """The data often has nothing for a bare brand name but matches the legal name ("<Name> Inc"),
    so try the name as given, then common suffixes, then a de-camel-cased form."""
    cands = [company] + [company + suf for suf in (' Inc', ' LLC', ' Corp', ' Technologies')]
    spaced = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', company.strip())
    if spaced != company.strip():
        cands += [spaced, spaced + ' Inc']
    for q in cands:
        rows = _parse(_fetch(q))
        if rows:
            return rows, q
    return [], company


def _load_cache():
    p = cache_path()
    if os.path.exists(p):
        try:
            return json.load(open(p))
        except Exception:
            return {}
    return {}


def lookup(company, force=False):
    cache = _load_cache()
    key = _norm(company)
    hit = cache.get(key)
    if hit and not force and time.time() - hit.get('_ts', 0) < CACHE_DAYS * 86400:
        return hit
    out = {'company': company, 'query': company, 'count_all': 0, 'count_recent': 0, 'employers': [],
           'median_wage': None, 'years': {}, 'verdict': 'unknown', '_ts': time.time()}
    try:
        rows, out['query'] = _rows_for(company)
        ambiguous = False
        if not rows and ' ' in key:  # retry with the first word ("Acme Robotics" -> "Acme")
            out['query'] = key.split()[0]
            rows = _parse(_fetch(out['query']))
            ambiguous = True
        # keep employers whose name contains the company's key word
        qn = _norm(out['query'])
        kw = (qn.split() or key.split() or [''])[0]
        rows = [r for r in rows if kw and re.search(r'(^| )' + re.escape(kw) + r'( |$)', _norm(r['employer']))]
        # A generic word matches many unrelated employers. Trust the match set when the company's own name
        # appears as an employer (then keep it plus its legal/group variants), or when the set is small;
        # otherwise call it ambiguous rather than counting strangers' filings.
        names = [key, qn]

        def _variant(e):
            n = _norm(e)
            for k in names:
                if n == k:
                    return True
                if k and n.startswith(k + ' ') and set(n[len(k):].split()) <= _SUFFIX_WORDS:
                    return True
            return False
        if any(_norm(r['employer']) in names for r in rows):
            rows = [r for r in rows if _variant(r['employer'])]
        elif ambiguous and [r for r in rows if key in _norm(r['employer'])]:
            rows = [r for r in rows if key in _norm(r['employer'])]
        elif len({r['employer'] for r in rows}) > 2:
            out['note'] = 'ambiguous: the name matches several unrelated employers'
            out['employers'] = sorted({r['employer'] for r in rows})[:5]
            rows = []
        out['count_all'] = len(rows)
        recent = [r for r in rows if r['year'] and r['year'] >= RECENT_FROM]
        out['count_recent'] = len(recent)
        if rows:
            emps = {}
            for r in rows:
                emps[r['employer']] = emps.get(r['employer'], 0) + 1
            out['employers'] = sorted(emps.items(), key=lambda x: -x[1])[:5]
        wages = [r['wage'] for r in recent if r['wage']]
        out['median_wage'] = int(statistics.median(wages)) if wages else None
        for r in rows:
            if r['year']:
                out['years'][str(r['year'])] = out['years'].get(str(r['year']), 0) + 1
        if out.get('note'):
            out['verdict'] = 'unknown'
        else:
            out['verdict'] = 'sponsors' if out['count_recent'] >= 5 else 'some' if out['count_recent'] >= 1 else 'none'
    except Exception as e:
        out['error'] = str(e)[:120]
    cache[key] = out
    p = cache_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump(cache, open(p, 'w'), indent=1)
    return out


def evidence(r):
    """One-line cell text for the tracker's 'H-1B Evidence' column."""
    if r.get('verdict') == 'unknown':
        return 'lookup ambiguous: check the employer name by hand' if r.get('note') else 'lookup failed'
    if r.get('verdict') == 'none':
        return 'no LCA filings found (startup or not a sponsor)'
    emp = r['employers'][0][0] if r.get('employers') else ''
    w = f", median ${r['median_wage']:,}" if r.get('median_wage') else ''
    return f"{r['verdict']}: {r['count_recent']} filings since {RECENT_FROM}{w} ({emp})"


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if '-h' in argv or '--help' in argv:
        print(__doc__)
        return 0
    names = [a for a in argv if not a.startswith('--')]
    res = [lookup(c, '--force' in argv) for c in names]
    if '--json' in argv:
        print(json.dumps(res, indent=1))
        return 0
    for r in res:
        emp = '; '.join(f'{e} ({n})' for e, n in r['employers'][:3]) if r['employers'] and isinstance(r['employers'][0], (list, tuple)) else '; '.join(r['employers'][:3])
        print(f"{r['company']:<24} {r['verdict']:<9} recent(>= {RECENT_FROM}): {r['count_recent']:<4} all: {r['count_all']:<5} "
              f"median ${r['median_wage'] or 0:,}  {emp}{'  ERR ' + r['error'] if r.get('error') else ''}")
    return 0


if __name__ == '__main__':
    sys.exit(main())

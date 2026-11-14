#!/usr/bin/env python3
"""Check that applications/<company>.md holds everything we need before a tab is closed.

Usage:
  python3 scripts/validate_application.py "<Company>" [--stage filled|submitted]

filled    (after Claude fills the form, before the candidate submits): form snapshot with answers,
          resume recorded, job description saved, tracker row linked.
submitted (after the candidate submits and the sheet is updated): all of the above, plus
          Status Applied (or later) and an applied date.
Exit code 0 = complete (or skipped because modules.record_keeping is off); 1 = something missing (listed).
Data location: the repo root, or $JOB_KIT_DATA if set.
"""
import argparse, glob, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_applications import company_key, dpath, profile, read_json, read_text, record_keeping_on, slug  # noqa: E402


def check(company, stage='submitted'):
    """Return (path, problems)."""
    path = dpath('applications', slug(company) + '.md')
    if not os.path.exists(path):
        return path, [f'MISSING file {path} (export the tracker, run build_applications.py)']
    md = read_text(path)
    problems = []
    forms = []
    for p in sorted(glob.glob(dpath('applications', '_forms', '*.json'))):
        try:
            d = read_json(p)
        except Exception:
            problems.append(f'unreadable snapshot {os.path.basename(p)}')
            continue
        if company_key(d.get('company', '')) == company_key(company):
            forms.append(d)
    live = [d for d in forms if 'recovered' not in d.get('source', '')]
    if not live:
        problems.append('no form snapshot from this batch in applications/_forms/')
    else:
        d = live[-1]
        if len([x for x in d.get('answers', []) if str(x.get('answer', '')).strip()]) < 2:
            problems.append('snapshot has fewer than 2 answered questions')
        if not (d.get('resume_uploaded') or d.get('files_attached')):
            problems.append('snapshot has no resume recorded')
    if 'Form snapshot' not in md:
        problems.append('company file has no "Form snapshot" section (rerun build_applications.py)')
    # check the job description of the role this snapshot belongs to (companies can have several roles)
    section = md
    jt = (live[-1].get('job_title') if live else '') or ''
    if jt:
        parts = re.split(r'\n(?=## )', md)
        hit = [x for x in parts if x.lower().startswith('## ' + jt.lower()[:25])]
        if hit:
            section = hit[0]
    if re.search(r'### Job description\s*\n\s*> \(not saved\)', section) or '### Job description' not in section:
        problems.append('job description not saved (tracker column N empty)')
    if not re.search(r'^\| Tracker \| .*row \d+', md, re.M):
        problems.append('no tracker row link (company not in tracker.csv; re-export the sheet)')
    if stage == 'submitted':
        st = re.findall(r'\| Status \| \*\*(.+?)\*\* \|', md)
        if not any(s in ('Applied', 'Interviewing', 'Rejected', 'Offer') for s in st):
            problems.append(f'status not Applied in company file (found {st or "none"}); update sheet, re-export, rebuild')
        if re.search(r'\| Applied date \| not recorded \|', md) and not re.search(r'\| Applied date \| \d', md):
            problems.append('applied date missing')
    return path, problems


def main(argv=None):
    ap = argparse.ArgumentParser(description='Check a company file is complete before closing its tab.')
    ap.add_argument('company')
    ap.add_argument('--stage', choices=['filled', 'submitted'], default='submitted')
    a = ap.parse_args(argv)
    if not record_keeping_on(profile()):
        print(f'SKIPPED {a.company} ({a.stage}): modules.record_keeping is off')
        return 0
    path, problems = check(a.company, a.stage)
    if problems:
        print(f'INCOMPLETE {a.company} ({a.stage}):')
        for p in problems:
            print(' -', p)
        return 1
    print(f'OK {a.company} ({a.stage}): {path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())

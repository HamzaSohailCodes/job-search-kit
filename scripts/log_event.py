#!/usr/bin/env python3
"""Append one event to applications/_events.jsonl (append-only history per application).

Usage:
  python3 scripts/log_event.py "<Company>" <event> [--role "<title>"] [--detail "..."] [--date YYYY-MM-DD]
         [--source email|check-status|apply-batch|manual] [--reason sponsorship|location|stack|domain|seniority|clearance|closed|pay|other|unknown]

Events: shortlisted, filled, submitted, skipped, interview, assessment, offer, rejected, withdrawn, note,
        followup (the candidate sent a follow-up or thank-you note), no_response (closed after the stale sweep)
Same (company, role, event, date, detail) is not written twice, so backfills are safe to rerun.
Data location: the repo root, or $JOB_KIT_DATA if set.
"""
import argparse, datetime, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_applications import dpath, read_text  # noqa: E402

EVENTS = ['shortlisted', 'filled', 'submitted', 'skipped', 'interview', 'assessment', 'offer', 'rejected', 'withdrawn', 'note', 'followup', 'no_response']
REASONS = ['sponsorship', 'location', 'stack', 'domain', 'seniority', 'clearance', 'closed', 'pay', 'other', 'unknown']


def events_path():
    return dpath('applications', '_events.jsonl')


def append(company, event, role='', detail='', date=None, source='manual', reason=''):
    path = events_path()
    rec = {'date': date or datetime.date.today().isoformat(), 'company': company.strip(), 'role': role.strip(),
           'event': event, 'detail': detail.strip(), 'source': source}
    if reason:
        rec['reason'] = reason
    key = (rec['company'].lower(), rec['role'].lower(), rec['event'], rec['date'], rec['detail'])
    if os.path.exists(path):
        for line in read_text(path).splitlines():
            try:
                o = json.loads(line)
            except Exception:
                continue
            if (o.get('company', '').lower(), o.get('role', '').lower(), o.get('event'), o.get('date'), o.get('detail', '')) == key:
                return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description='Append one event to applications/_events.jsonl.')
    ap.add_argument('company'); ap.add_argument('event', choices=EVENTS)
    ap.add_argument('--role', default=''); ap.add_argument('--detail', default='')
    ap.add_argument('--date'); ap.add_argument('--source', default='manual'); ap.add_argument('--reason', choices=REASONS)
    a = ap.parse_args(argv)
    if a.date:
        try:
            datetime.date.fromisoformat(a.date)
        except ValueError:
            ap.error(f'--date must be YYYY-MM-DD, got {a.date!r}')
    ok = append(a.company, a.event, a.role, a.detail, a.date, a.source, a.reason or '')
    print('logged' if ok else 'duplicate, not logged')
    return 0


if __name__ == '__main__':
    sys.exit(main())

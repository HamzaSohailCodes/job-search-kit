---
name: dedupe-before-sheet-write
description: Run check_dupes.py on the final rows against the full tracker before pasting any Shortlisted rows
metadata:
  type: feedback
---
Before writing any rows to the tracker, run
`python3 .claude/skills/search-jobs/scripts/check_dupes.py --rows <rows.json> --tracker tracker/tracker.csv`
on the final rows from every source and require exit 0. The same role often appears on several boards with
different URLs and slightly different titles; per-source filters miss these.

**Why:** duplicates in the tracker are noticed at once and cost trust in every other row.
**How to apply:** export the tracker fresh before the check; treat WARN lines (same company already Applied or
Rejected for the same role family) as a judgment call and say so in the notes. Related: [[application-record-lifecycle]].

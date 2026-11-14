---
name: application-record-lifecycle
description: Every application is recorded in applications/<company>.md and validated before its tab is closed
metadata:
  type: feedback
---
Per application (when `modules.record_keeping` is on): fill the form → `scripts/pin_resume.sh` → save a form snapshot
and log a `filled` event → rebuild `applications/<company>.md` → the candidate submits (Claude never does) → mark the
tracker row Applied with the date and log `submitted` → export the tracker once per batch and rebuild →
`python3 scripts/validate_application.py "<Company>" --stage submitted` prints OK → only then close the tab →
commit at the end of the batch.

**Why:** every rejection should be reviewable against the exact job description, resume and answers sent.
**How to apply:** never close a tab whose record fails validation; if a gap can't be fixed, note it in the company
file and tell the candidate. Related: [[dedupe-before-sheet-write]].

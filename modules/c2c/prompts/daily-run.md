# Daily contract run (paste into Claude Code, opened at the repo root)

```
Run today's contract day. First run python3 modules/c2c/scraper/run.py --check-config; if no contract
type is picked, tell me to add one with /setup → update my profile (targets.employment_types) and stop. Read modules/c2c/README.md, modules/c2c/prompts/*.md, soul.md,
profile/answer_bank.md and profile/stories.md.

1. Replies: check my inbox (inbox, spam and bounces) for anything since the last run, if an inbox
   connector is available. List replies and bounces, match them to tracker rows, and propose updates to
   Outcome / Next Step (O). Draft answers to replies in the recruiter-email style; do not send.
2. Follow-ups: list contract rows whose Follow-up 1 (AB) or Follow-up 2 (AC) date is today and that have no reply.
   Draft the follow-ups from modules/c2c/prompts/follow-up-and-calls.md.
3. Search: run /search-contract-jobs 1 (scraper, only my contract types, dedupe against the whole
   tracker, one role per company, companies contacted today removed). Show me the shortlist with score,
   title, company, employment type, rate / terms and resume to use.
4. After I approve: open each approved posting so I can apply (pre-fill only, never submit), then run
   contacts.py and modules/c2c/outreach/build_outreach.py and show me every email draft.
5. After I approve the drafts: I send them myself. Then update the tracker rows (F status,
   AA = contacted date, O = outreach stage) and verify the sheet.
6. Save the run to batches/<date>-c2c/ (scored jobs, shortlist, apply log, drafts) and add a dated
   line to batches/c2c-status.md.

Rules: one application and one email per company per day; no rate, visa or location in any email;
keep only the contract types I picked; skip onsite/hybrid, clearance, rates below pay.hourly_floor and
roles asking more than c2c.max_years_asked years, plus citizenship or GC-only roles that I don't qualify
for; one tracker tab for every work type; never send, submit or change a profile.
```

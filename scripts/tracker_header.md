# Tracker columns (A..AC)

The tracker is one Google Sheet tab (`tracker.sheet_id`, tab `tracker.tab`, always addressed by `tracker.gid`,
default `0`). Every role goes in this one tab, whatever its work type: full-time, part-time and contract
(W2, C2C, 1099) rows sit side by side and are told apart by column L. There is no separate C2C tab. `tracker/tracker.csv` is a full CSV export of that tab, header row included. Every script here reads
that export; none of them writes to the sheet.

Paste this header into row 1 of an empty tab (tab-separated, so it lands in A1..AC1):

```
Job Title	Company	Location	Job Link	Pay Scale	Apply Status	Applied Date	Job Posted At	Notes	Match Score	Source	Employment Type	Application Issues	Job Description	Outcome / Next Step	Reason Tag	H-1B Evidence	Reached Interview	Rate / Terms	Priority	Recruiter Email	Recruiter Name / LinkedIn	Resume to Send	Email Subject	Email Body	LinkedIn Note	Contacted On	Follow-up 1	Follow-up 2
```

Never add, rename, reorder or delete columns: `build_applications.py` reads A..Q by position, the others
by header name (exact text below). Older exports that stop at Q or R still work.

| Col | Header | Format | Written by | Read by |
|---|---|---|---|---|
| A | Job Title | Exact title from the posting | search-jobs | all (by header in followups, calibrate) |
| B | Company | Employer name as on its own site; the company file is `applications/<slug>.md` | search-jobs | all |
| C | Location | `City, ST (Remote/Hybrid/On-site)`, e.g. `Austin, TX (Hybrid)`, `Remote (US)` | search-jobs | build_applications |
| D | Job Link | Posting URL (LinkedIn: `https://www.linkedin.com/jobs/view/<id>/`). Rows are found by this column. | search-jobs | build_applications, followups |
| E | Pay Scale | e.g. `$160K–$210K/yr`, or `Not listed` | search-jobs | build_applications |
| F | Apply Status | One of the statuses below | search-jobs (`Shortlisted`), apply-batch (`Applied`, `Skipped`, `Blocked`), review-emails (`Rejected`, `Interviewing`, `Offer`) | all |
| G | Applied Date | `YYYY-MM-DD` (also accepted: `M/D/YYYY`) | apply-batch after the candidate submits | followups, calibrate, Dashboard |
| H | Job Posted At | `YYYY-MM-DD`; prefix `~` when estimated from a relative age | search-jobs | build_applications |
| I | Notes | One line: strongest evidence, key gap, eligibility unknowns. Add `resume: <label>` (a `resumes[].label` from config, or `tailored`) when the resume is chosen. | search-jobs, apply-batch | build_applications, calibrate |
| J | Match Score | Integer 0–100 | search-jobs | calibrate (score bands) |
| K | Source | `LinkedIn`, `Indeed`, `Glassdoor`, `Ashby — official company careers`, `Greenhouse — …`, `Lever — …`, `Email`, `Referral` | search-jobs, review-emails | calibrate |
| L | Employment Type | `Full-time`, `Part-time`, `Contract (W2)`, `Contract (C2C)`, `Contract (1099)` or `Not stated` (labels from `core.config.EMPLOYMENT_TYPES`). Only types in `targets.employment_types` are shortlisted; `Not stated` rows are kept and flagged in Notes. | search-jobs, search-contract-jobs | build_applications, calibrate (segment), check_dupes |
| M | Application Issues | Anything that blocked or complicated the form | apply-batch | build_applications |
| N | Job Description | Full posting text (required before validate `--stage filled` passes) | search-jobs / apply-batch | build_applications, validate_application, guard_jobs |
| O | Outcome / Next Step | One line: outcome, stated reason, next step with a date | review-emails, follow-ups | build_applications, followups, Dashboard |
| P | Reason Tag | `sponsorship`, `location`, `stack`, `domain`, `seniority`, `clearance`, `closed`, `pay`, `other`, `unknown` | review-emails, follow-ups (stale sweep: `unknown`) | calibrate, Dashboard |
| Q | H-1B Evidence | Only with `modules.h1b`: the company's visa-filing history (`sponsors: …`, `some: …`, `no LCA filings found…`). Leave blank otherwise; keep the column. | search-jobs (h1b module) | build_applications, calibrate (H-1B tier) |

| R | Reached Interview | `Yes` once a role gets any interview, recruiter call or assessment; kept when it is later rejected | review-emails | calibrate |

### Contract and outreach columns (S..AC)

Filled for contract rows by `/search-contract-jobs` (`modules/c2c/outreach/build_outreach.py`); blank on most
full-time rows. Usable for any role where the candidate emails a recruiter directly.

| Col | Header | Format | Written by |
|---|---|---|---|
| S | Rate / Terms | e.g. `$85/hr C2C, 6 months, remote`; `C2C not stated` when the post is silent | search-contract-jobs |
| T | Priority | `A` (score ≥ 85 and C2C confirmed), `B` (good match or terms not stated), `C` (weak) | search-contract-jobs |
| U | Recruiter Email | Named recruiter or the shared apply inbox from the post | search-contract-jobs (`contacts.py`) |
| V | Recruiter Name / LinkedIn | Only when certain (named in the post, or first.last@ address) | search-contract-jobs |
| W | Resume to Send | A file in `resumes/c2c/` or a `resumes[].label` | search-contract-jobs |
| X | Email Subject | Draft; the candidate sends | build_outreach / build_emails |
| Y | Email Body | Draft; the candidate sends | build_outreach / build_emails |
| Z | LinkedIn Note | Draft connection note, under 300 characters | build_outreach |
| AA | Contacted On | `YYYY-MM-DD`, set when the candidate says they sent it | search-contract-jobs |
| AB | Follow-up 1 | Sheet formula: `WORKDAY(AA, c2c.followup_workdays[0])` | build_outreach |
| AC | Follow-up 2 | Sheet formula: `WORKDAY(AA, c2c.followup_workdays[1])` | build_outreach |

For contract rows the outreach stage lives in O (Outcome / Next Step), using these words at the start:
`Not contacted`, `Emailed`, `Connected`, `Replied`, `Screen call`, `Submitted (RTR)`, `Client interview`, then the
usual F statuses (`Interviewing`, `Offer`, `Rejected`). Score goes in J, years asked and skills matched in I.

## Apply Status values

`Shortlisted`, `Applied`, `Interviewing`, `Offer`, `Rejected`, `Skipped`, `Blocked`, `Pending Review`, `Closed`.

- `build_applications.py` writes a company file for rows in `Applied`, `Rejected`, `Interviewing`, `Offer`
  (change with `--statuses`) and for any company with a form snapshot.
- `followups.py` looks at `Applied` and `Interviewing` only.
- There is no "No response" status: the stale sweep keeps `Applied` and sets O and P instead.
- Rows in `Skipped` or `Closed` still count as duplicates: never re-add them.
- Dedupe runs across every work type: the same role found as full-time on an ATS and as C2C on Dice is one row.

## Rules for writing to the sheet

- Navigate to the `#gid=<tracker.gid>` URL and confirm `location.hash` before typing; never write to another tab.
- Type single cells through the Name Box (jump to e.g. `O42`, check the Name Box shows that cell, then type).
  If a filter is on, a jump to a hidden row lands on the next visible row: check before typing.
- Diff the full export before and after an edit session; no other row may change.
- Re-export to `tracker/tracker.csv` and run `python3 scripts/build_applications.py` after every edit session.

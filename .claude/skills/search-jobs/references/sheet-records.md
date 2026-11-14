# Sheet records

## 1. Get write access

- Use the Google Sheets connector with the `google-workspace` skill when one is connected. Read its Sheets
  reference before writing.
- Otherwise use the candidate's logged-in Chrome (`tracker.chrome_profile_name`) to open the sheet and paste rows
  (tab-separated text into the first empty row of column A). Read the sheet back after pasting.
- Fast read in Chrome: from the open sheet tab,
  `fetch(location.pathname.replace(/\/edit.*$/,'/gviz/tq') + '?tqx=out:csv&gid=<tracker.gid>')` returns the whole tab
  as CSV (add `&range=A400:N460` for a slice, `&tq=select A,B,D,F` for columns). Parse it with a quote-aware CSV
  parser: the Notes cells contain commas. Save the full export as `tracker/tracker.csv` (record keeping reads it).
- If the account shows "You need access", stop. Don't request access on the candidate's behalf. Save rows to
  `$R/rows.json` and tell the candidate which account needs editor access.

## 2. Read before writing

1. Read the header row. Map each field below to the existing column whose header means the same thing
   (case- and wording-insensitive). **Never add, rename, reorder or delete columns.** Leave a field out when the
   sheet has no matching column.
2. Read every existing row (all tabs if the tracker splits jobs across tabs) to build the dedupe index.
3. If the sheet is empty (no header), write the standard header from `scripts/tracker_header.md` first.

### 2a. Tracker columns (the kit's standard layout, A–AC; this skill writes A–Q)

| Col | Header | What to write |
|---|---|---|
| A | Job Title | Exact title from the posting |
| B | Company | Employer name as on its own site |
| C | Location | `City, ST (Remote/Hybrid/On-site)`, e.g. `Austin, TX (Hybrid)`, `Remote (US)`. The work mode goes in parentheses. |
| D | Job Link | Employer posting URL. For LinkedIn use `https://www.linkedin.com/jobs/view/<id>/` |
| E | Pay Scale | As posted, e.g. `$150K–$190K/yr`, or `Not listed` |
| F | Apply Status | `Shortlisted` for rows this skill adds. Other values: `Applied`, `Interviewing`, `Offer`, `Rejected`, `Skipped`, `Blocked`, `Closed`, `Pending Review`. Never change them. |
| G | Applied Date | Leave blank |
| H | Job Posted At | `YYYY-MM-DD`; prefix `~` when estimated from a relative age |
| I | Notes | `SEARCH <date> | resume: <label> | <strongest CV evidence>; gap: <key gap>; <eligibility unknowns>` |
| J | Match Score | Integer 0–100 (search-workflow §4) |
| K | Source | The portal that found it: `sources.py` prints the text per portal (`LinkedIn`, `Handshake`, `Indeed`, `Ashby — official company careers`, …; an extra portal's `name`). Table in `defaults.md` → Sources |
| L | Employment Type | `Full-time`, `Part-time`, `Contract (W2)`, `Contract (C2C)`, `Contract (1099)` or `Not stated` (from the posting; see defaults.md → Work types). Only types in `targets.employment_types`; `Not stated` rows say so in I. |
| M | Application Issues | Leave blank; skip reasons go here later (e.g. `Skipped: posting says no visa sponsorship`) |
| N | Job Description | Full plain-text posting (up to ~30,000 characters; a cell holds 50,000) |
| O | Outcome / Next Step | Leave blank (`/review-emails` fills it) |
| P | Reason Tag | Leave blank |
| Q | H-1B Evidence | Only when `modules.h1b` is on: `h1b_lookup.evidence()` text (`sponsors: N filings since …`, `some: …`, `no LCA filings found…`). Blank otherwise. |

R (Reached Interview) and S..AC (contract and outreach columns, filled by `/search-contract-jobs`) stay blank on
rows this skill adds; `build_rows.py` writes all 29 columns so a paste lines up. The resume label in Notes is one
of `resumes[].label` in the profile. When checking duplicates, rows with
`Skipped` or `Closed` still count: never re-add them.

## 3. Deduplicate

A job is a duplicate when any of these match an existing row or an earlier row in this run:

- The same normalized URL (lowercase host, drop query strings and tracking such as `utm_*`, `trk`, `refId`,
  trailing slash), or the same job ID (Indeed `jk`, Greenhouse/Lever/Ashby posting ID). For LinkedIn the ID is the
  trailing number in either URL form (`/jobs/view/<id>/` or `/jobs/view/<slug>-<id>/`), or `currentJobId=`.
- The same normalized company + title (lowercase, strip "Inc", "LLC", punctuation, level words and location noise).
- The same company and title posted on another board: keep the one with the employer URL.
- Across work types: a role already in the tab as `Contract (C2C)` (e.g. from `/search-contract-jobs`) is a
  duplicate of the same full-time role, and the other way round.

**Hard gate before any write:**
`python3 .claude/skills/search-jobs/scripts/check_dupes.py --rows $R/rows.json --tracker tracker/tracker.csv`
on the final rows (full export; older exports that stop at Q or R work too). It must exit 0. It catches the same role on a different
board URL, level and hyphen wording ("Full-Stack" vs "Senior Full Stack"), duplicates inside the batch, and prints
WARN when the company is already Applied/Interviewing/Rejected/Offer for the same role family: decide those, don't
add them blindly. Add `--rows-done <earlier rows.json>` for rows written after the export. Every candidate set
(ATS filter output, LinkedIn, Indeed, Glassdoor, curated lists) goes through it.

Never overwrite or change an existing row. If a duplicate has new information (salary now listed, reposted),
report it in the summary instead of editing the row, unless the candidate asks.

## 4. Write

- Append after the last non-empty row in one batch, ranked best first. **gviz CSV skips empty rows**, so the
  export's row count is not a row number: confirm the first empty row with per-row range reads
  (`&range=A<n>:D<n>` empty, the row above filled).
- Before writing through the Name Box: navigate to the `edit#gid=<tracker.gid>` URL and confirm
  `location.hash === '#gid=<gid>'` (writes go to whichever tab is active). Find the Name Box with `find`
  ("Name Box") and click its ref — never by coordinate — then cmd+A, type the cell, Return, and confirm
  `document.querySelector('#t-name-box').value` is the target before pasting.
- Paste `LC_ALL=en_US.UTF-8 pbcopy < $R/rows.tsv` (without `LC_ALL` en-dashes and emoji get mangled) and paste
  values **immediately**: the candidate's own copying can overwrite the clipboard.
- The grid has a fixed row count; a paste past the end fails with "exceeds the sheet size". Before a big batch,
  insert rows at the bottom first. Paste in chunks of ~40 rows and read each chunk back.
- Write dates and salary as plain text so Sheets doesn't reinterpret them.
- Never touch the status or applied date of existing rows.

## 5. Verify

Read the appended range back and compare titles and links with `rows.json`. Compare a fresh export with the
pre-paste export to prove the rows above are unchanged. Check the row count and that there are no duplicates.
Fix anything wrong (cmd+Z first if a paste landed in the wrong place) before reporting.

## 6. Report

End with:

- The sheet link (`config.sheet_url`) and tab.
- Jobs added (count, plus the top 5 with title, company, score).
- Duplicates skipped and other exclusions by reason.
- Coverage: sites × queries done, pages read, anything blocked or partial, and the next page to resume from.
- Eligibility unknowns the candidate should check.

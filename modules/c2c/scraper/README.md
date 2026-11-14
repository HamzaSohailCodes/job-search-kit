# C2C job finder

Finds remote US contract jobs of the types the candidate picked (`targets.employment_types`: C2C, W2, 1099)
and scores them against the candidate's profile (`config/profile.json`). No installs needed: Python 3.9+ standard library only. Run from the repo root.

## Run

```bash
python3 modules/c2c/scraper/run.py --check-config   # effective settings and search terms, no network
python3 modules/c2c/scraper/run.py                  # Dice + LinkedIn + staffing-firm sites, window = c2c.days
python3 modules/c2c/scraper/run.py --only dice      # Dice only (the useful part)
python3 modules/c2c/scraper/run.py --days 7         # shorter window
python3 modules/c2c/scraper/run.py --rescore batches/<date>-c2c/raw_jobs_<date>.json   # re-filter, no network
```

Results go to `batches/<today>-c2c/c2c_jobs_<date>.csv`, best score first, with Employment Type (the tracker
label for column L, `Not stated` when unclear) and Rate / Terms, plus `raw_jobs_<date>.json`.
A full run takes about 5–10 minutes, because it waits 1 second between requests to each site (4 s on LinkedIn).

## Where jobs come from

- **Dice**: searches "Third Party" jobs (Dice's tag for roles that accept C2C) when C2C is picked, all
  contract jobs otherwise, plus keyword searches among all contract jobs. Each job page's badges
  ("Contract Corp To Corp", "Contract W2", "Contract Independent") set the contract types; a listing whose
  badges name only types the candidate did not pick is dropped.
- **LinkedIn**: the public (logged-out) job search, remote + contract. It rate-limits quickly; when job
  pages are refused, the rest are kept as search-card leads.
- **Staffing-firm sites** (optional): copy `firm_boards.example.json` to `firm_boards.json` (git-ignored) and
  list boards a plain script can read. Without the file, firm sites are skipped.

## Change the search

Edit `config/profile.json`: `targets.employment_types`, `pay.hourly_floor`, `current_role.years_experience`
and `level`, `targets.skills`, `targets.titles`, and the `c2c` section (window, remote, max years asked, title include/exclude lists, queries). See
`settings.py` for every key and its default, and `modules/c2c/README.md` for the table.

## Score

0–100, weighted: skills 35, experience 25, seniority 15, domain 10, logistics (C2C + remote) 15.
Logistics is full when a picked contract type is confirmed, 85 when C2C is picked and the post names visas
(H1B, GC-EAD; vendors that take outside contractors usually do), 65 when the post doesn't say.

## Other files

- `contacts.py`: apply type, apply email and Dice contract types for each Dice job in a CSV.
- `firms.txt`, `detect_platforms.py`, `probe_boards.py`, `platforms.txt`: a survey of ~60 staffing
  firms' career sites (public company sites) used to decide which ones a plain script can read.

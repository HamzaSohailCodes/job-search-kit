# Standing defaults

Personal settings come from `config/profile.json` (written by `/setup`; field notes in `config/README.md`).
This file turns them into search rules that apply on every run. An explicit instruction in the current chat
overrides any line here or in the profile; a lasting change goes into the profile.

## Sources

Search **only** the portals in `search.sources` (known ids, in priority order) plus `search.extra_portals`
(portals the candidate added in `/setup`). `python3 .claude/skills/search-jobs/scripts/sources.py --query "<title>"`
prints that list for this profile with login status, playbook and column K text. Anything else needs the
candidate's say-so in chat. Ids not in the list below are reported and skipped (they belong in `extra_portals`).

| id | Portal | Login? | Column K (Source) | Playbook (`search-workflow.md` §2) |
|---|---|---|---|---|
| `linkedin` | LinkedIn Jobs | yes | `LinkedIn` | LinkedIn |
| `handshake` | Handshake (students, recent grads, early career) | yes | `Handshake` | Handshake |
| `indeed` | Indeed | no | `Indeed` | Indeed |
| `glassdoor` | Glassdoor | wall after a few pages | `Glassdoor` | Glassdoor |
| `ashby` | Ashby boards (jobs.ashbyhq.com) | no | `Ashby — official company careers` | Ashby |
| `greenhouse` | Greenhouse boards | no | `Greenhouse — official company careers` | Greenhouse and Lever |
| `lever` | Lever boards | no | `Lever — official company careers` | Greenhouse and Lever |
| `wellfound` | Wellfound (startups) | yes | `Wellfound` | Wellfound |
| `dice` | Dice (tech) | no | `Dice` | Dice |
| `ziprecruiter` | ZipRecruiter | no | `ZipRecruiter` | ZipRecruiter |
| `builtin` | Built In | no | `Built In` | Built In |
| `yc` | YC Work at a Startup | yes | `YC Work at a Startup (ycombinator.com/jobs)` | YC Work at a Startup |
| `wttj` | Welcome to the Jungle | no | `Welcome to the Jungle` | Welcome to the Jungle |
| `usajobs` | USAJOBS (US federal) | no | `USAJOBS` | USAJOBS |
| `weworkremotely` | We Work Remotely | no | `We Work Remotely` | Remote boards |
| `remoteok` | Remote OK | no | `Remote OK` | Remote boards |
| `company_pages` | Employers' own career pages | no | `Company careers page` | Company career pages |
| extra portal | `search.extra_portals[].name` | `login_required` | the portal's `name` | Extra portals |

- **Login portals** (`linkedin`, `handshake`, `wellfound`, `yc`, and extra portals with `login_required`): use the
  candidate's own Chrome profile (`tracker.chrome_profile_name`: `list_connected_browsers` → `select_browser`).
  First check the profile is signed in (the page shows the candidate's account, not a sign-in form). If it
  isn't, stop that portal and ask the candidate to sign in themselves, then carry on with the others. Never
  type credentials, never sign in or create an account for them.
- Pace browser portals like a person: 8–20 s (varied) between page loads; stop a portal at the first
  "unusual activity", rate-limit or CAPTCHA page and report it.
- Ashby / Greenhouse / Lever run every time they are listed: `apply-batch/scripts/fetch_ats.py` fetches every
  board in `apply-batch/scripts/slugs/` in one go.
- **Curated hiring lists**, only when `search.curated_linkedin_lists` is true: public LinkedIn creators or pages
  that regularly post "companies hiring" lists, plus public niche job boards (playbook: `search-workflow.md` →
  Curated hiring lists). The candidate picks them; they live in `search.curated_sources` as
  `[{"name", "url", "note"}]`. Store only the person/page, never the companies (they change every week). Ask
  before following anyone on the candidate's behalf.
- Whatever portal found a job, verify it on the employer's own page when one exists and use that link in
  column J; K still names the portal that found it.

Do not use paid job-search APIs unless the candidate asks.

## Destination tracker

- Google Sheet `tracker.sheet_id`, tab `tracker.tab`, addressed by `gid=tracker.gid` (never "the first sheet":
  a Dashboard tab may sit in front). Link: `config.sheet_url(p)`.
- One tab for every work type. Columns: the layout in `scripts/tracker_header.md` (A–AC), mapped in
  `sheet-records.md` §2. Re-read the header each run in case it changed. Never create a separate contract tab.
- If there is no sheet yet, keep rows in `tracker/tracker.csv` with that header and say so.
- If the sheet says "You need access", stop and tell the candidate which account must be given edit access.

## Posting window

- `search.posting_window_days` (default 7), counted back from the start of the run in `locations.timezone`.
- Prefer the newest postings: a job posted in the last 24–72 hours ranks above an equally good older one.

## Location and work mode

- Remote (US-eligible) roles only if `locations.remote_us_ok` is true.
- If `locations.relocation_anywhere_us` is true, on-site and hybrid roles anywhere in the US are fine; only roles
  whose offices are all outside the US are excluded.
- Otherwise hybrid and on-site roles must be in `locations.onsite_hybrid_areas` (regex `locations.match_regex`;
  `core/config.py` → `loc_regex`). Exclude them elsewhere.
- Read the description, not just the card: "remote" cards often say "hybrid 3 days in <city>" in the body.
  For ATS postings check the real office list (`location` + `secondaryLocations`).
- "Remote" roles restricted to certain states or countries: exclude when the candidate's state
  (`identity.state`) isn't covered; flag unclear ones.

## Work types (column L)

- Wanted: `targets.employment_types`. Labels for column L: `Full-time`, `Part-time`, `Contract (W2)`,
  `Contract (C2C)`, `Contract (1099)`, or `Not stated` (`core.config.employment_label`).
- Read the type from the ATS field (Ashby `employmentType`, Lever `categories.commitment`, Greenhouse metadata),
  else the title ("(Contract)", "Part-Time") and the description ("6-month contract", "C2C", "1099", "W2").
- Drop types the candidate didn't pick: part-time unless `part_time`; contracts unless a contract type. A contract
  whose kind isn't stated is kept when any contract type is picked (L `Not stated`, Notes say
  `contract; W2/C2C/1099 not stated`). Internships always drop.
- Keep `Not stated` rows; Notes say `employment type not stated`.
- Contract rates: skip when the posted hourly rate tops out below `pay.hourly_floor`.
- Dice third-party / staffing-vendor contracts are `/search-contract-jobs`, same tracker tab.

## Agencies and travel

- Recruiting-agency postings: include only if `logistics.agencies_ok`. Prefix their Notes with
  `AGENCY: ask the recruiter for the employer name (and sponsorship, if needed) before applying`.
  Always skip pure aggregator reposts (Jobgether, Lensa, Dice reposts, Jobright, "Jobs via …"): they duplicate
  real postings.
- Travel: exclude roles needing more than `logistics.travel_max_percent`; mention the percentage in Notes.

## Work authorization

For everyone: exclude roles that require a security clearance the candidate doesn't hold, and roles that
require US citizenship when the candidate isn't a citizen (`work_authorization.citizenship`).

Only when `work_authorization.needs_sponsorship` is true:
- **Blocked** (exclude, reason "sponsorship"): "no visa sponsorship", "sponsorship and transfers are not
  available", "must be authorized to work without current or future sponsorship", "US citizens only",
  "green card holders only", "U.S. persons only". `scripts/screen.py` → `SPONSOR_BLOCK` catches the common
  wordings; read the description anyway.
- **OK**: the posting mentions visa sponsorship or transfers, or says nothing. When it says nothing, add
  `sponsorship unknown` to Notes. Rank explicit "sponsorship available" above an equal job that says nothing.
- If `modules.h1b` is on: drop companies on `profile/no_sponsor_companies.txt` (they said so in writing), and
  look up each shortlisted company's filing history (`modules/h1b/README.md`). The history is evidence for
  ranking, never a knockout by itself. Ask about sponsorship in the first recruiter reply.

## Role exclusions

- Titles matching `targets.title_exclude_regex` or `targets.skip_levels_regex`; keep titles matching
  `targets.title_include_regex` (or close variants of `targets.titles`).
- Roles requiring more than `targets.max_years_required` years.
- Postings whose primary stack is a knockout in `targets.other_stack_knockouts` (with none of
  `targets.primary_stack_regex`), and domains in `targets.domain_skips`.
- Pay: skip roles whose posted range tops out below `pay.floor` (check the employer's ATS posting: board
  listings are often wrong or missing).
- Closed postings (the employer page is gone or says it no longer accepts applications).

## Ranking lessons (general)

- Postings that name tools on the candidate's resume (`targets.skills`) and match the scope of their best work
  rank higher than generic matches.
- A same-day rejection is usually a knockout (sponsorship, location, years, stack), not a resume read. When
  rejections come in, `/review-emails` records the reason; feed real patterns back into the profile's
  `targets.*` rules rather than into one-off judgment.
- Referrals and agency recruiters work: when a top company has a contact path, note it in Notes.

## Deduplication

Never add a job that already exists in the tracker, and never add a second role at a company the candidate has
already applied to, been rejected by or skipped (WARN lines from `check_dupes.py`: decide, don't add blindly).
Check before every write, as `sheet-records.md` §3 describes.

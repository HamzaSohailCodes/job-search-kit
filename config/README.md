# config/profile.json

The one file of personal settings. `/setup` writes it (the questions it asks are in
`.claude/skills/setup/references/questions.md`); you can edit it by hand. After any edit run
`python3 scripts/doctor.py`. Scripts read it through `core/config.py`, which fills any key you leave out
from `profile.example.json`. Tests point `JOB_KIT_PROFILE` at `tests/fixtures/profile.json` instead.

| Section | Field | Used for |
|---|---|---|
| `identity` | name, contact, links, address | Form filling, resume header, output filenames (`Jane_Doe_Resume.pdf`) |
| `current_role` | `company`, `title`, `years_experience`, `level` | Years knockout, C2C level filter, forms |
| `resumes` | `[{label, path, use_for}]` | Which base resume goes with which roles; paths are relative to the repo |
| `targets` | `titles` | Search queries |
| | `employment_types` | Any of `full_time`, `part_time`, `contract_w2`, `contract_c2c`, `contract_1099`. Only these types are shortlisted; any contract type turns on `/search-contract-jobs`. Written to tracker column L as `Full-time`, `Contract (C2C)`… |
| | `title_include_regex`, `title_exclude_regex` | Title filter in search and apply |
| | `max_years_required` | Postings asking for more years fail the gate |
| | `skip_levels_regex` | Level knockouts on the title (staff, manager…) |
| | `primary_stack_regex` | The stack a posting should lead with (gate warns otherwise) |
| | `other_stack_knockouts`, `domain_skips` | `[{regex, label}]` knockouts with the label shown in reports. Mind `\b` next to `.`/`#`: use `\.net\b\|\bc#`, not `\b(\.net\|c#)\b` |
| | `scope_regex`, `domain_prefer_regex` | Kinds of work and domains to boost in the match score (gate warns when scope is missing) |
| | `skills.core`, `skills.ai` | Match scoring and C2C keyword filters |
| `locations` | `remote_us_ok`, `onsite_hybrid_areas`, `match_regex` | Location filter |
| | `relocation_anywhere_us` | When true, any US location passes; only non-US offices fail |
| | `location_answer` | What forms get for "location" |
| `work_authorization` | `needs_sponsorship`, `visa_status`, `any_employer_answer`, `security_clearance`… | Form answers; "no sponsorship" postings fail only when `needs_sponsorship` |
| `pay` | `floor`, `ask_when_no_range`, `position_in_posted_range`, `round_to` | Pay filter and salary answers (yearly roles) |
| | `hourly_floor`, `part_time_hours_per_week` | Rate filter for contract roles; hours for part-time |
| `logistics` | notice, travel, agencies, recording consent, "how did you hear" | Form answers |
| `screening` | `age_18_plus`, `background_check_ok`, `drug_test_ok`, `drivers_license`, `reliable_transportation`, `hybrid_days_max`, `weekends_ok`, `overtime_ok`, `open_to_contract_to_hire`, `previously_employed_answer`, `relatives_at_company`, `accommodations`, `remote_setup`, `timezone_overlap`, `current_salary_answer`, `compensation_notes`, `cover_letter` (`only_when_required`/`always`/`never`), `portfolio_url`, `writing_sample`, `references`, `languages[]`, `certifications[]`, `licenses[]` | The screening questions most forms ask. Any value `"ask"` = leave that field for the candidate |
| `education` | `[{degree, field, school, year}]` | Form answers |
| `education_summary` | `highest_level`, `student_status`, `graduation_date`, `gpa`, `gpa_scale`, `share_gpa` (`share`/`only_when_required`/`never`), `honors` | Education questions; Handshake |
| `eeo` | gender, Hispanic/Latino, race, veteran, `veteran_detail[]`, `military_spouse`, disability, sexual orientation, transgender | Voluntary self-identification; "Decline to self-identify" is always valid |
| `tracker` | `sheet_id`, `tab`, `gid`, `chrome_profile_name` | Google Sheet tracker; Sheet1 must be `gid=0` |
| `inbox` | `gmail_address` | `/review-emails` |
| `search` | `posting_window_days`, `batch_size`, `sources` (ids in `core.config.KNOWN_SOURCES`; default LinkedIn, Handshake, Indeed + Ashby/Greenhouse/Lever boards), `extra_portals` (`[{name, url, search_url with {query}, login_required, notes}]`), `curated_linkedin_lists`, `curated_sources` (`[{name, url, note}]`) | `/search-jobs` and `/apply-batch` defaults |
| `modules` | `h1b`, `resume_tailoring`, `record_keeping` | Optional features; off means skipped |
| `h1b` | `min_known_sponsor_share` (0.7), `max_none_per_batch` (3) | Batch mix guidance when `modules.h1b` is on |
| `resume_build` | `content_path`, `pages`, `exact_pages`, `engine` (`latex`/`html`), `font`, `chrome_path`, `tailoring_mode` (`70/30` or `full`), `batch_size`, `batch_days`, `min_score` | Resume engine and `/build-batch-resume`. Short resume? set `pages: 1`. Details: `resume/README.md` |
| `c2c` | `remote_only`, `days`, `max_years_asked`, `queries`, `title_include`/`title_exclude`, `min_score`, `shortlist_min_score`, `skip_clearance`, `firm_boards_file`, `resume_versions`, `followup_workdays`, `outreach` | Contract search, used only when a contract type is in `employment_types`. Details: `modules/c2c/README.md` |
| `calibration` | `role_types` (`[[name, regex]]`) | Role segments in `scripts/calibrate.py` (empty = built-in list) |
| `followups` | `quiet_days`, `max_followups`, `stale_days`, `thankyou_days`, `checkin_days` | `/follow-ups` timing |
| `writing` | `style_notes` | Voice for drafted answers (with `soul.md`) |

Environment variables (mainly for tests): `JOB_KIT_PROFILE` (another profile file), `JOB_KIT_DATA` (another data
folder for records), `H1B_CACHE`, `H1B_RECENT_FROM`, `JOB_KIT_RESUME_CONTENT` and `JOB_KIT_SKILLS_INVENTORY` (other resume inputs).

One-off overrides for a single run: `EXTRA_LOC_OK="california|\bca\b" python3 ...` adds locations without editing the file.

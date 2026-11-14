# Job search kit

Run your job search with Claude Code: find roles that fit, tailor a resume per posting, pre-fill
applications in your own Chrome (you click Submit), keep a record of every application, review your inbox,
draft follow-ups and prepare for interviews.

Nothing personal is in this repo until you run setup. All your settings end up in one file,
`config/profile.json`, and your records live in your own private copy of this repo.

## Setup (about 25 minutes)

**You need:** macOS or Linux, Python 3.9+, git, Claude Code (desktop app or CLI) with the
**Claude in Chrome** extension connected to the Chrome profile you use for LinkedIn and Google, and your
resume as PDF or DOCX. Optional: `brew install gh tectonic poppler` (GitHub checks and PDF resumes).

1. **Get your own private copy.** On GitHub, click "Use this template" → make it **Private**. Clone it.
2. **Part 1, the machine:**
   ```bash
   ./setup.sh
   ```
   Checks your tools, creates `.venv`, creates the data folders and copies starter files into `profile/`,
   `memory/` and `soul.md`. Safe to re-run; it never overwrites your files.
3. **Part 2, you:** open Claude Code in this folder and run **`/setup`**. Claude starts with your CV, then asks
   the questions most application forms ask (gender, race, veteran and disability status, work authorization,
   start date, relocation, background check, salary and so on; "decline" or "ask me each time" are always
   fine), then work types (full-time, part-time, contract W2/C2C/1099), which job portals to search besides
   LinkedIn, Handshake and Indeed, your target roles, optional modules, tracker sheet and Chrome profile. It
   shows you a summary, then writes `config/profile.json` and your profile files and creates the tracker sheet.
4. **Check:**
   ```bash
   ./setup.sh --doctor
   ```
   Fix anything marked ✗. Warnings (!) are fine to leave.

## Daily use

| Say | What happens |
|---|---|
| `/search-jobs` | Finds new postings (default last 7 days), filters and scores them, adds them to your sheet as Shortlisted. |
| `/build-batch-resume 15` | A tailored resume for each top Shortlisted job, from your facts only. |
| `/apply-batch 15` | Pre-fills each application in its own Chrome tab. **Never submits.** You review and submit. |
| "check status" | Marks the ones you submitted as Applied and records each one. |
| `/review-emails` | Weekly: reads your job-search inbox, updates statuses, logs rejections with reasons. |
| `/follow-ups` | Drafts follow-ups and thank-you notes for you to send. |
| `/interview-prep <company>` | Prep pack from what you actually sent, plus a mock interview. |
| `/cv-job-match` | Reviews your CV and suggests roles. |
| `/search-contract-jobs` | Contract roles (W2/C2C/1099) from Dice and staffing vendors, if you picked a contract work type. Same tracker tab. |
| "update my profile" | Changes any answer from setup. |

## Work types

`/setup` asks which kinds of work you want: full-time, part-time, contract W2, contract C2C, contract 1099
(`config/profile.json` → `targets.employment_types`). Everything goes into **one tracker tab**; the
Employment Type column tells rows apart, and dedupe works across types. Picking any contract type turns on
`/search-contract-jobs` and the contract outreach columns (rate, recruiter, email drafts, follow-up dates).

## Optional modules

Turned on or off in `config/profile.json` → `modules` (setup asks):

- `h1b`: visa-sponsorship evidence per company and a no-sponsor list. For candidates who need sponsorship.
- `resume_tailoring`: tailored PDF/DOCX resumes (needs `tectonic` and `poppler`).
- `record_keeping`: one file per company with the posting, resume sent, answers and a timeline.

## What it will never do

Click Submit; tick consent, privacy, terms or arbitration boxes; answer CAPTCHAs, bot checks or questions aimed
at AI; write essays on forms that ask for no AI; sign in or create accounts; enter passwords, SSNs or bank
details; send any email or message for you. It leaves those for you and lists them in its report.

## Layout

| Path | What |
|---|---|
| `setup.sh`, `.claude/skills/setup/` | The two parts of setup |
| `config/` | `profile.example.json` (every setting, with defaults), `README.md` (what each field does) |
| `core/config.py` | The loader every script uses |
| `CLAUDE.md` | House rules Claude reads in this folder |
| `.claude/skills/`, `.claude/agents/` | The skills and the resume-reviewer agent (they load only in this folder) |
| `scripts/` | Shared tools: `doctor.py`, records, follow-ups, calibration, posting guards, sheet styling |
| `modules/h1b/`, `modules/c2c/` | Visa-sponsorship evidence; contract search |
| `resume/` | Resume engine and PDF checks |
| `templates/` | Starter files `setup.sh` copies |
| `tests/` | `python3 -m unittest discover -s tests` (uses a fake "Jane Doe" profile) |
| `profile/`, `soul.md`, `memory/`, `applications/`, `batches/`, `resumes/`, `tracker/`, `reviews/`, `followups/`, `interview-prep/` | Your data, created by setup |

## Privacy

Your copy holds contact details, work authorization and EEO answers: keep it **private**. `doctor.py` fails if
the GitHub repo is public. Never commit tokens, cookies, Gmail exports or API keys (`.gitignore` covers the
common ones).

## Contributing to the kit

Improvements go to the template repo, never with personal data. Before a PR run the tests: one of them
reads your `config/profile.json` (if you have one) and fails if your name, email or phone appears anywhere in
the tooling folders (`core/`, `scripts/`, `.claude/`, `modules/`, `resume/`, `templates/`, `tests/`).
```bash
python3 -m unittest discover -s tests
```

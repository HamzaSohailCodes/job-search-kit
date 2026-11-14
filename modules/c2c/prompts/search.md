# Contract search criteria

Source of truth for the code: `config/profile.json` (mapped in `modules/c2c/scraper/settings.py`) and
`modules/c2c/scraper/filters.py`. This file says the same in words. Run
`python3 modules/c2c/scraper/run.py --check-config` to see the values in effect.

## Who
The candidate in `config/profile.json`, for the contract types in `targets.employment_types`
(`contract_c2c`, `contract_w2`, `contract_1099`): `current_role.level`, `current_role.years_experience`,
skills from `targets.skills.core` and `targets.skills.ai`. If `work_authorization.needs_sponsorship` is
true, C2C works only through an employer's corp, and 1099 / independent is never kept.

## Where
- Dice, remote: "Third Party" listings (Dice's tag for C2C) when C2C is picked, all contract listings
  otherwise, plus keyword searches among all contract jobs ("c2c react", "w2 contract react", "1099 react";
  "h1b python" only when the candidate needs sponsorship).
- LinkedIn contract + remote searches.
- Optional staffing-firm boards in `modules/c2c/scraper/firm_boards.json`.

Search terms come from `c2c.queries`; empty lists are generated from `targets.titles`, `targets.skills` and
the contract types picked.

## Keep
- Titles matching `c2c.title_include` and none of `c2c.title_exclude` (defaults: full stack, software
  engineer/developer, Python, React, Node, TypeScript, AI/GenAI/LLM/agentic engineer, backend, tech lead,
  architect; not data/enterprise/solutions/cloud architect).
- Remote in the US when `c2c.remote_only`. Posted within the window (`c2c.days`, default 30; 1 for daily runs).

## Drop
Titles in `c2c.title_exclude` (defaults: Java, .NET, Angular, Salesforce, SAP, QA, DevOps/SRE, mobile,
Go/Rust/PHP/Ruby, junior, manager/director); posts that confirm only contract types the candidate did not pick
(e.g. "W2 only" when only C2C is picked); a posted hourly rate topping out below `pay.hourly_floor`;
onsite or hybrid; remote outside the US;
clearance (`c2c.skip_clearance`); "US citizens only" unless the candidate is one; "GC/USC only",
"no H-1B" or "no sponsorship" when the candidate needs sponsorship; more than `c2c.max_years_asked` years asked.

## Score (0–100)
Skills 35, experience 25, seniority 15, domain 10, logistics (C2C + remote) 15. Minimum kept:
`c2c.min_score` (55); shortlist minimum `c2c.shortlist_min_score` (70).
Logistics is 100 when a picked contract type is confirmed, 85 when C2C is picked and the post names visas
(H1B/GC-EAD, usually a vendor that takes outside contractors), 65 when not stated.

## Employment Type (tracker column L)
The first picked type the post confirms, in the order C2C, W2, 1099 (Dice badges first, then the text):
`Contract (C2C)`, `Contract (W2)`, `Contract (1099)`. `Not stated` when the post doesn't say: kept, flagged in
Notes, and the recruiter is asked. Rate / Terms (S) holds the posted rate and what was found, e.g.
`$85-95/hr, C2C confirmed, remote` or `C2C not stated`.

## Resume choice
`c2c.resume_versions`: the `ai` version for AI/LLM/agentic roles, `lead` for lead/architect roles,
`default` for everything else (missing keys use `default`). A `resumes[].label` is used as is; other names
are files in `resumes/c2c/`.

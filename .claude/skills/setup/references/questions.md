# Question bank for /setup

The questions application forms ask most often, in the order /setup asks them, each with the config key it
fills. The aim: after /setup, apply-batch can answer almost every field on a typical form without asking again.

How to ask:
- Use `AskUserQuestion`, up to 4 questions per call, 2–4 options each. The tool always adds "Other" for free
  text, so when a list is longer than 4, show the most common choices and let "Other" take the rest.
- Put "Decline to self-identify" first on every EEO question. EEO is voluntary and never affects eligibility;
  say so once before the EEO round.
- Skip a question when the CV already answers it. Show what you read and ask for corrections instead.
- Skip a question that doesn't apply (e.g. GPA when they graduated more than ~5 years ago and aren't using
  Handshake; contract questions when no contract type is picked).
- "Ask me each time" is always a valid answer: store `"ask"` and apply-batch leaves that field for the candidate.
- Never build options from guesses about the person. Options come from what the CV or the candidate said, or
  are neutral. In particular, never infer languages, race, ethnicity, religion, citizenship or visa status from
  names, countries or cities on the CV. Example: languages not on the CV → options "English only" · "English
  and other languages (name them)" · "Prefer not to list"; then ask the level of each (Native · Fluent ·
  Professional · Conversational).

## Never ask or store

These stay with the candidate on every form; /setup doesn't ask about them and apply-batch leaves them blank:
SSN or national ID numbers, date of birth, passwords, bank or card details, driver's license number, criminal
history, health details beyond the voluntary disability form, SMS/marketing consent, and anything a form
marks as a legal attestation.

## Round A: from the CV (confirm, don't re-ask)

| Field | Config key |
|---|---|
| Legal full name, preferred name | `identity.full_name`, `identity.preferred_name` |
| Email, phone | `identity.email`, `identity.phone` |
| City, state, ZIP, country | `identity.city`, `identity.state`, `identity.zip`, `identity.country` |
| LinkedIn, GitHub, portfolio/website | `identity.linkedin`, `identity.github`, `identity.website` |
| Current employer and title, years of experience, level | `current_role.*` |
| Degrees (degree, field, school, year) | `education[]` |
| Certifications and licenses | `screening.certifications[]`, `screening.licenses[]` |
| Languages (only if listed on the CV; otherwise ask with neutral options, see "How to ask") | `screening.languages[]` |

Then ask only what the CV lacks: pronouns (optional), name pronunciation (optional), street address
(optional; many forms require it), and the location line for forms (e.g. "Austin, TX (open to relocation)").

## Round B: voluntary self-identification (EEO)

Say first: "These are the voluntary questions most US forms ask. Your answers are saved once and reused;
'Decline to self-identify' is always fine."

| Question | Options (first is the default) | Config key |
|---|---|---|
| Gender | Decline to self-identify · Male · Female · Non-binary (Other for anything else) | `eeo.gender` |
| Are you Hispanic or Latino? | Decline to self-identify · Yes · No | `eeo.hispanic_latino` |
| Race | Decline to self-identify · White · Asian · Black or African American (Other: American Indian or Alaska Native, Native Hawaiian or Other Pacific Islander, Two or more races) | `eeo.race` |
| Veteran status | Decline to self-identify · I am not a protected veteran · I identify as one or more protected veteran categories · I am a veteran but not protected | `eeo.veteran` |
| Protected veteran categories (only if they said protected) | Disabled veteran · Recently separated veteran · Active duty wartime or campaign badge veteran · Armed Forces service medal veteran (multiSelect) | `eeo.veteran_detail[]` |
| Military spouse or dependent (some forms ask) | Decline · Yes · No | `eeo.military_spouse` |
| Disability (Form CC-305 wording) | Decline to self-identify · Yes, I have a disability (or previously had one) · No, I do not have a disability | `eeo.disability` |
| Sexual orientation (some forms) | Decline to self-identify · Heterosexual · Gay or lesbian · Bisexual (Other for the rest) | `eeo.sexual_orientation` |
| Transgender (some forms) | Decline to self-identify · Yes · No | `eeo.transgender` |
| Pronouns | Leave blank · she/her · he/him · they/them | `identity.pronouns` |

## Round C: work authorization

| Question | Options | Config key |
|---|---|---|
| Legally authorized to work in the US? | Yes · No | `work_authorization.authorized_in_us` |
| Will you now or in the future need visa sponsorship? | No · Yes | `work_authorization.needs_sponsorship` |
| Current status (if sponsorship or asked) | US citizen · Green card · H-1B (needs transfer) · F-1 OPT / STEM OPT (Other: TN, L-2, H-4 EAD, O-1…) | `work_authorization.visa_status` |
| "Authorized for any employer / without restriction"? (only with an employer-specific visa) | No (usual) · Yes · Ask me each time | `work_authorization.any_employer_answer` |
| Citizenship (only for export-control questions) | Leave for me · enter country | `work_authorization.citizenship` |
| Security clearance held | None · Secret · Top Secret / TS-SCI · Other | `work_authorization.security_clearance` |
| Are you at least 18? | Yes · No | `screening.age_18_plus` |

## Round D: logistics and screening

| Question | Options | Config key |
|---|---|---|
| Earliest start / notice period | Immediately · 2 weeks · 1 month · Other | `logistics.notice_period` |
| Open to relocation? | No · To specific areas · Anywhere in the US | `locations.relocation_anywhere_us`, `locations.onsite_hybrid_areas` |
| Work setting | Remote only · Remote or hybrid · Any (remote, hybrid, on-site) | `locations.remote_us_ok`, `screening.hybrid_days_max` |
| Max days in office per week (if hybrid OK) | 1–2 · 3 · 4–5 · Any | `screening.hybrid_days_max` |
| Max travel | None · Up to 10% · Up to 25% · Up to 50% | `logistics.travel_max_percent` |
| Willing to undergo a background check? | Yes · Ask me each time | `screening.background_check_ok` |
| Willing to take a drug test? | Yes · Ask me each time | `screening.drug_test_ok` |
| Valid driver's license / reliable transportation? | Yes · No · Ask me each time | `screening.drivers_license`, `screening.reliable_transportation` |
| Weekends, evenings, on-call or overtime OK? | Yes · Sometimes · No | `screening.weekends_ok`, `screening.overtime_ok` |
| Open to contract-to-hire? | Yes · No | `screening.open_to_contract_to_hire` |
| Bound by a non-compete or similar agreement? | No · Yes · Leave for me | `logistics.non_compete` |
| Previously worked at / applied to a company before? | Answer No, verify per company · Ask me each time | `screening.previously_employed_answer` |
| Relatives or friends working at the company? | Answer No, verify per company · Ask me each time | `screening.relatives_at_company` |
| Interview recording / AI notetaker consent | Yes · No · Ask me each time | `logistics.recording_consent` |
| Accommodations needed for interviews? | No · Leave for me | `screening.accommodations` |
| Reliable remote setup (quiet space, internet)? (remote roles) | Yes · Ask me | `screening.remote_setup` |
| Hours you can overlap (remote roles) | US Eastern · US Central · US Pacific · Flexible | `screening.timezone_overlap`, `locations.timezone` |
| How did you hear about us (default) | LinkedIn · Indeed · Handshake · Company website | `logistics.how_did_you_hear_default` |

## Round E: compensation

| Question | Options | Config key |
|---|---|---|
| Minimum base salary (full-time) | free text number | `pay.floor` |
| Ask when no range is posted | free text number | `pay.ask_when_no_range` |
| Where to answer inside a posted range | 75% of the way up (default) · Midpoint · Top of range | `pay.position_in_posted_range` |
| Current or most recent salary (some forms; several states ban asking) | Prefer not to say (default) · Give a number · Ask me each time | `screening.current_salary_answer` |
| Minimum hourly rate (contract or part-time picked) | free text number | `pay.hourly_floor` |
| Hours per week (part-time picked) | free text number | `pay.part_time_hours_per_week` |
| Benefits or equity must-haves | free text, optional | `screening.compensation_notes` |

## Round F: education details (students, recent grads, or Handshake)

| Question | Options | Config key |
|---|---|---|
| Highest level completed | High school · Associate · Bachelor's · Master's (Other: PhD, bootcamp…) | `education_summary.highest_level` |
| Currently a student? | No, graduated · Yes, undergraduate · Yes, graduate | `education_summary.student_status` |
| Graduation date (or expected) | free text YYYY-MM | `education_summary.graduation_date` |
| GPA and scale, and share it? | Share · Only when required · Never | `education_summary.gpa`, `education_summary.gpa_scale`, `education_summary.share_gpa` |
| Relevant coursework or honors | free text, optional | `education_summary.honors` |

## Round G: documents and links

| Question | Options | Config key |
|---|---|---|
| Cover letters | Only when required (default) · Always · Never | `screening.cover_letter` |
| Portfolio, writing sample or work samples to attach | free text URLs, optional | `screening.portfolio_url`, `screening.writing_sample` |
| References | "Available upon request" (default) · I'll give names per company | `screening.references` |

## Round H: work types and job portals

Work types (multiSelect): Full-time · Part-time · Contract W2 · Contract C2C (Other: Contract 1099,
internship) → `targets.employment_types`. Follow-ups per type are in SKILL.md step 4.

Job portals. Say: "I search LinkedIn, Handshake and Indeed by default, plus company career boards on Ashby,
Greenhouse and Lever. Do you want to add any other job portals?" Ask with multiSelect, two questions if needed:

| Portal | Source id | Notes |
|---|---|---|
| Glassdoor | `glassdoor` | |
| Wellfound (AngelList Talent) | `wellfound` | Startups; needs a login |
| Dice | `dice` | Tech; contract-heavy (also used by the contract search) |
| ZipRecruiter | `ziprecruiter` | |
| Built In | `builtin` | City tech hubs |
| Y Combinator Work at a Startup | `yc` | Needs a login |
| Welcome to the Jungle (Otta) | `wttj` | |
| USAJOBS | `usajobs` | US federal roles |
| Remote boards (We Work Remotely, Remote OK) | `weworkremotely`, `remoteok` | Remote only |
| Company career pages they care about | `company_pages` | Ask for the list of companies |

Anything else ("Other"), e.g. a niche industry board, a university board or a local site: ask for its name,
URL, a search URL if they have one, and whether it needs a login, and save it to `search.extra_portals[]` as
`{name, url, search_url, login_required, notes}`. For portals that need a login, ask which Chrome profile is
signed in. Handshake needs one too, and the candidate's school account.

Defaults: `search.sources` = `["linkedin", "handshake", "indeed", "ashby", "greenhouse", "lever"]` plus whatever
they add. If they say Handshake doesn't apply (not a student or recent grad, no school account), remove it.

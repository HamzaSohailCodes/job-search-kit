---
name: follow-ups
description: Find the candidate's quiet applications and draft short follow-up notes, interview thank-you notes and check-ins for them to send themselves, and propose closing applications with no reply after the stale window (followups.* in config/profile.json). Reads the tracker export and applications/_events.jsonl; never sends anything. Use for "follow ups", "who should I chase", "draft follow-ups", "thank-you note for <company>", "stale applications", or "/follow-ups [days]".
---

# Follow-ups

Drafts only. Claude never sends a follow-up, email, LinkedIn note or ATS message; the candidate sends each one
themselves. All paths are relative to the repo root.

Timing comes from `config/profile.json`: `followups.quiet_days` (default 10), `followups.max_followups` (2),
`followups.stale_days` (60), and the optional `followups.thankyou_days` (3) and `followups.checkin_days` (7).
`scripts/followups.py` reads them; a number the user gives in chat (`/follow-ups 14`) overrides `--days`.

Contract rows live in the same tracker tab (column L = `Contract (W2)`, `Contract (C2C)` or `Contract (1099)`).
Once the candidate has emailed a recruiter (AA `Contacted On` set), their follow-up dates come from AB
`Follow-up 1` and AC `Follow-up 2` (or AA + `c2c.followup_workdays`, default 3 and 5 workdays), not from
`quiet_days`. Two follow-ups at most; a row whose O starts with `Replied`, `Screen call`, `Submitted (RTR)` or
`Client interview` gets none. Column meanings: `scripts/tracker_header.md`.

## 1. Refresh and list
1. Export the tracker tab to `tracker/tracker.csv` (`/export?format=csv&gid=<tracker.gid>`) so statuses and dates
   are current. Run `/review-emails` first if it hasn't run in the last 3 days: a reply already in the inbox must
   not get a follow-up.
2. `python3 scripts/followups.py [--days <N>]`
   Buckets: follow up, thank-you due, interviewing check-in, stale, undated. Contract items show
   `contacted <date> | due <date>` and carry `"contract": true` in `--json`.
3. Show the candidate the list as a table (best-fit roles first; with `modules.h1b` on, known sponsors first),
   at most 15 follow-ups per day. Undated rows: ask for the date or take it from the `submitted` event; don't guess.

## 2. Pick the channel (per application, in this order)
Contract rows: reply in the same thread as the first outreach email, to the recruiter in U/V. The drafts in X/Y
(subject, body) show what was already said; `modules/c2c/prompts/follow-up-and-calls.md` has the follow-up
wording. Full-time rows:
- A named recruiter or hiring manager who wrote to the candidate (see the Timeline in `applications/<company>.md`
  or the mail).
- The ATS's own message thread if it has one (Ashby candidate portal, Greenhouse "My applications").
- The hiring manager or recruiter on LinkedIn, only if the candidate already knows who they are. Don't look people
  up and don't add contacts.
- None of these: skip it and say so. A cold note to a generic jobs@ inbox is not worth sending.

## 3. Draft
Read `applications/<company>.md` (posting, resume sent, form answers), `soul.md` (voice, Never list) and
`writing.style_notes` in the profile. Every claim must already be in what was submitted; a follow-up adds no new
skills, metrics or stories.
- **Follow-up** (about 60 to 90 words): the role and the date applied, one line tying the strongest matching proof
  to the posting's top must-have, one line of interest in something specific the company does (from the posting,
  not a guess), a polite ask about next steps. No visa line, no pay, no "just checking in".
- **Second follow-up** (only if the first was `quiet_days`+ days ago, about 40 words): short and polite, then stop.
  `max_followups` is the limit.
- **Thank-you** (within 24 hours of a call that happened, about 70 words): thank the interviewer by first name, name
  one thing from the conversation (ask the candidate what was discussed), restate fit in one line, availability for
  next steps. The `interview` event also covers invites, so confirm the call took place.
- **Interviewing check-in** (quiet `checkin_days`+ days): ask for the next step and timeline in two sentences.
- **Contract follow-up 1** (on the AB date, about 40 to 60 words, same thread): the role and the rate/terms from S
  as first sent, availability, one line of fit; ask whether the client is still interviewing.
  **Follow-up 2** (on the AC date, about 30 words): a short last nudge, then stop.
- Plain text, first person, concise. Greet by first name only when sure of it.

Write the drafts to `followups/<today>.md`: one section per application with row, company, role, channel,
recipient, subject line (for email) and the body. Show them in chat too.

## 4. After the candidate sends
For each one they confirm sent:
`python3 scripts/log_event.py "<Company>" followup --role "<title>" --detail "<channel>: <first or second> follow-up | thank-you" --source manual`
Then add one line to column O (Outcome / Next Step) through the Name Box, after confirming the tab is
`#gid=<tracker.gid>` (find the row by Job Link, column D): `Follow-up sent <date> via <channel>; next check <date + quiet_days>`.
For contract rows keep the stage word at the start of O and append to it, e.g.
`Emailed 2026-10-27; follow-up 1 sent <date>`. Never overwrite AB/AC (they are sheet formulas from AA).

## 5. Stale sweep (`stale_days`+ days, no reply)
Propose, never apply on your own: list them and ask "Close these as no response?". On the candidate's yes, per row:
column O = `No response after <N> days (closed <today>)`, column P = `unknown`, keep F = `Applied` (there is no
No Response status; the Dashboard counts by O and P), and
`python3 scripts/log_event.py "<Company>" no_response --role "<title>" --detail "no reply after <N> days" --source manual`.
A company closed this way can be applied to again after 90 days with a different role.

## 6. Finish
Run `python3 scripts/build_applications.py`, then report counts (drafted, sent, closed). Commit only when the
candidate asks.

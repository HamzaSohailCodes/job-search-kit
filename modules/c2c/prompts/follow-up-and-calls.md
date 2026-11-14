# Follow-ups, LinkedIn and calls

Drafts in the same style as the first email: no rate, visa or location. The candidate sends them.
Sign with the candidate's first name (`identity.preferred_name`, else the first word of `identity.full_name`).

## Follow-up 1 (`c2c.followup_workdays[0]` workdays after, default 3; tracker column AB)
> Hi [name], just checking you saw my note about the [role] role. I'm still interested and happy to hop on a quick call whenever works for you. Thanks, [first name]

## Follow-up 2 (`c2c.followup_workdays[1]` workdays after, default 5; tracker column AC)
> Hi [name], one last note on [role]. If it's already filled, no problem. Please keep me in mind for other remote [2–3 core skills] contracts you're working on. Thanks, [first name]

After the second follow-up, stop on that role. Recruiters who replied once go on a warm list; draft them a short availability note every 2–3 weeks.

Reply in the same thread (keeps the resume and context). Only to people who haven't replied.

## LinkedIn
- Connection note (under 300 characters): role + "I applied and emailed my resume" + one keyword match.
  `build_outreach.py` drafts one per row.
- After they accept: "Thanks for connecting, [name]. I applied to your [role] role and sent my resume by email. Any chance we could talk for 10 minutes this week?"
- Under ~20 connection requests a day.

## Phone call
Opener (30 seconds): "Hi [name], this is [full name]. I applied for your [role] on Dice yesterday and emailed you my resume. Is the role still open, and is there a good time to talk about it?"

Ask:
- Who is the end client? Are you the prime vendor?
- Is it really C2C (or W2 / 1099, whichever was picked)? If the candidate needs sponsorship: how does the employer side work for their visa?
- Rate range for the role (don't give a number first).
- Interview rounds and contract length.

Have ready: start date, interview times, a 2-minute intro, and one story each for the role's main themes
(see `profile/stories.md`).

## RTR
Sign a Right to Represent with only one vendor per end client. Log it in the tracker row's Notes (I).

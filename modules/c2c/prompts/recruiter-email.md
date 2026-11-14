# Recruiter first email

Built by `modules/c2c/outreach/build_emails.py` (and `build_outreach.py`). Use this to write or check one by hand.
These are drafts: the candidate reviews and sends every email.

## Rules
- About 120 words, plain text, resume attached (the one in Resume to Send, column W).
- Subject: `<Role title> – <Full name> | <2–3 keywords from the JD>`. Clean messy titles
  (drop "- USA Canada", plurals, version numbers).
- Greeting: first name only when certain (named in the contacts file, or a first.last@ address);
  otherwise "Hi there,".
- Opener names the role and where the candidate applied ("I applied on Dice for your … role") and one line
  on who they are that matches the role family (AI / full-stack / backend / lead): `c2c.outreach.openers`,
  or generated from `current_role.level` and `current_role.company`.
- Three bullets. Each starts with the JD's own must-have wording, then one proof line from
  `c2c.outreach.proof`, naming the employer or client where the resume does. Ignore "nice to have" skills.
  No side-project names.
- Ask "Is this fully remote, or is some onsite time expected?" only when the JD hints at onsite or hybrid.
- Close with `c2c.outreach.closing` (empty = the default "I'm free most afternoons this week for a quick call. Resume
  attached.") then the signature (name, phone, LinkedIn from `identity`).
- Never: rate, visa or work authorization, location, years per skill.
- Proof lines come only from `profile/master_cv.md` / `profile/answer_bank.md`. No new metrics. A bullet
  that still says `[add one proof line ...]` must be filled or cut before the draft is shown as ready.

## Writing proof lines

In `config/profile.json`:

```json
"c2c": {
  "outreach": {
    "proof": {
      "rag": "built a RAG pipeline (embeddings, LangChain) for <product>, grounding answers in retrieved data",
      "react": "at <employer>, rebuilt <product area> end to end in React and Node.js, growing engagement <n>%",
      "lead": "tech lead for <n> engineers at <employer>"
    }
  }
}
```

Built-in topics: rag, agents, llm, evals, docai, react, node, graphql, python, sql, aws, azure, health, lead.
A custom topic adds `"patterns": ["regex", ...]` for the JD phrases it answers.

## Example shape

Subject: Senior AI Engineer – <Full name> | LangGraph, RAG, LLM Evals

> Hi [first name],
>
> I applied on Dice for your Senior AI Engineer role. I'm a senior AI engineer, currently at <employer>. Here's how I match what you're looking for:
>
> • Multi-agent workflows / tool calling: <proof line for agents>.
> • Vector stores / hybrid search: <proof line for rag>.
> • Evaluation suites / LLM observability: <proof line for evals>.
>
> Is this fully remote, or is some onsite time expected?
>
> I'm free most afternoons this week for a quick call. Resume attached.
>
> Thanks,
> <Full name>
> <phone> · <linkedin>

## Sending (the candidate does this)
Schedule for weekday mornings in the recruiter's time zone, a few minutes apart. Named recruiters first,
shared/ATS inboxes later. Before sending, check: To, subject, greeting, role phrase, signature, attachment.

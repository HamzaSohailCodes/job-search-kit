"""Tracker rows (A..AC, the one tracker tab; layout in scripts/tracker_header.md) for shortlisted contract roles,
with the outreach columns S..AC filled.

Drafts only: subjects, bodies and LinkedIn notes are for the candidate to review and send.

Usage (repo root):
  python3 modules/c2c/outreach/build_outreach.py --jobs batches/<date>-c2c/shortlist.csv \
      [--contacts batches/<date>-c2c/contacts_shortlist.csv] [--raw .../raw_jobs_<date>.json] \
      --first-row <sheet row of the first job> [--out batches/<date>-c2c/tracker_rows.tsv]

Writes two TSVs: tracker_rows.tsv (A..AC, to paste as new rows) and outreach_S-AC.tsv (S..AC only, to paste
over rows already in the tracker). Contract rows: Title A, Company B, Location C, Link D, Pay E,
Status F = Shortlisted, Posted H, Notes I (years asked + skills matched), Score J, Source K,
Employment Type L, Job Description N, O = outreach stage ("Not contacted"), then S..AC.

Config read: identity.full_name, work_authorization.needs_sponsorship, targets.employment_types,
resumes[].label, c2c.resume_versions {"ai", "lead", "default"} (missing keys fall back to "default"; a value
that is a resumes[].label is used as is, anything else as <First_Last>_Resume_<value> in resumes/c2c/),
c2c.followup_workdays [3, 5], plus build_emails.py's keys.
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_emails as be  # noqa: E402
from build_emails import config  # noqa: E402

HEADER = ["Job Title", "Company", "Location", "Job Link", "Pay Scale", "Apply Status", "Applied Date",
          "Job Posted At", "Notes", "Match Score", "Source", "Employment Type", "Application Issues",
          "Job Description", "Outcome / Next Step", "Reason Tag", "H-1B Evidence", "Reached Interview",
          "Rate / Terms", "Priority", "Recruiter Email", "Recruiter Name / LinkedIn", "Resume to Send",
          "Email Subject", "Email Body", "LinkedIn Note", "Contacted On", "Follow-up 1", "Follow-up 2"]
S = HEADER.index("Rate / Terms")  # 18: first outreach column
DESC_MAX = 49000  # a Google Sheets cell holds 50,000 characters
TYPE_WORDS = {"contract_c2c": r"corp\s*to\s*corp|c2c|third party", "contract_w2": r"\bw-?2\b",
              "contract_1099": r"independent|1099"}


def resume_version(p, title):
    v = {"default": "FullStack"}
    v.update({k: x for k, x in (config.get(p, "c2c.resume_versions") or {}).items() if x})
    t = title.lower()
    if re.search(r"\b(ai|ml|llm|genai|gen ai|generative|agentic|machine learning|rag|nlp|data scien)\b", t):
        key = "ai"
    elif re.search(r"\b(lead|architect|principal|manager|head)\b", t):
        key = "lead"
    else:
        key = "default"
    name = v.get(key) or v["default"]
    labels = {r.get("label") for r in config.get(p, "resumes", []) or []}
    return name if name in labels else f"{config.file_stem(p)}_Resume_{name}"


def wanted_types(p):
    sponsor = config.needs_sponsorship(p)
    return [t for t in config.employment_types(p) if t in config.CONTRACT_TYPES
            and not (t == "contract_1099" and sponsor)]


def contacts_check(p, contract_types):
    """Dice contract types from contacts.py ("Corp To Corp, W2"). Returns "" when they fit the candidate's
    picks (or are unknown), else a short reason to skip."""
    ct = (contract_types or "").lower()
    if not ct:
        return ""
    found = [t for t, rx in TYPE_WORDS.items() if re.search(rx, ct)]
    if not found or set(found) & set(wanted_types(p)):
        return ""
    return "Dice lists only " + "/".join(config.employment_label(t).replace("Contract ", "").strip("()") for t in found)


def priority(score, label, skip=""):
    if skip:
        return "Skip"
    confirmed = label not in ("", "Not stated")
    return "A" if score >= 85 and confirmed else ("B" if score >= 70 else "C")


def source_name(s):
    s = s or ""
    if s.lower().startswith("dice"):
        return "Dice"
    if s.lower().startswith("linkedin"):
        return "LinkedIn"
    if s.startswith("firm:"):
        return f"{s[5:]} (staffing firm)"
    return s


def notes(r, label):
    parts = []
    if r.get("Years asked"):
        parts.append(f"years asked: {r['Years asked']}")
    if r.get("Skills matched"):
        parts.append(f"skills: {r['Skills matched']}")
    if label in ("", "Not stated"):
        parts.append("employment type not stated: ask the recruiter")
    return "; ".join(parts)


def linkedin_note(fname, title, chosen):
    keys = [be.tidy(lab or be.LABEL_DEFAULT.get(tp, tp)) for _, tp, lab, proof in chosen if proof != be.PLACEHOLDER]
    match = f" My {keys[0]} work is a close match." if keys else ""
    note = (f"Hi {fname or 'there'}, I just applied to your {be.short(title, 45)} role and emailed my resume."
            f"{match} Would be great to connect.")
    return note[:300]


def _score(r):
    try:
        return int(float(r.get("Score") or 0))
    except ValueError:
        return 0


def tracker_row(p, r, desc="", contact=None, row_no=2, drafts=True):
    """One shortlisted job (scraper CSV dict) -> 29 cells A..AC."""
    c = contact or {}
    fu1, fu2 = (list(config.get(p, "c2c.followup_workdays") or []) + [3, 5])[:2]
    title, link = r.get("Title", ""), r.get("Link", "")
    label = r.get("Employment Type") or "Not stated"
    email = c.get("Apply email", "")
    fname = be.first_name(email, c.get("First name", ""))
    skip = contacts_check(p, c.get("Contract types", ""))
    terms = r.get("Rate / Terms") or ("C2C not stated" if "contract_c2c" in wanted_types(p) else "Terms not stated")
    if skip:
        terms = f"{terms} ({skip})"
    subj = body = note = ""
    if drafts:
        subj, body, chosen = be.compose(p, title, desc, r.get("Source", ""), fname)
        note = linkedin_note(fname, title, chosen)
    row = [title, r.get("Company", ""), r.get("Location", ""), link, r.get("Pay") or "Not listed", "Shortlisted", "",
           r.get("Posted", ""), notes(r, label), str(_score(r)), source_name(r.get("Source", "")), label, "",
           (desc or "")[:DESC_MAX], "Not contacted", "", "", "",
           terms, priority(_score(r), label, skip), email, fname, resume_version(p, title), subj, body, note, "",
           f'=IF(AA{row_no}="","",WORKDAY(AA{row_no},{fu1}))', f'=IF(AA{row_no}="","",WORKDAY(AA{row_no},{fu2}))']
    assert len(row) == len(HEADER)
    return row


def build_rows(p, jobs, descs, contacts, first_row=2, drafts=True):
    return [tracker_row(p, r, descs.get(r.get("Link", "").split("?")[0], ""),
                        contacts.get(r.get("Link", "").split("?")[0], {}), first_row + i, drafts)
            for i, r in enumerate(jobs)]


def write_tsv(path, rows, header=HEADER):
    with open(path, "w") as f:
        f.write("\n".join("\t".join(be.cell(x) for x in row) for row in [header] + rows) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", required=True)
    ap.add_argument("--contacts")
    ap.add_argument("--raw")
    ap.add_argument("--first-row", type=int, default=2, help="sheet row number of the first job (for formulas)")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    p = config.load()
    if not config.module_on(p, "c2c"):
        sys.exit(be.MODULE_OFF)
    rows = build_rows(p, be.read_rows(a.jobs), be.load_descriptions(a.jobs, a.raw), be.load_contacts(a.contacts),
                      a.first_row)
    out = a.out or os.path.join(os.path.dirname(os.path.abspath(a.jobs)), "tracker_rows.tsv")
    write_tsv(out, rows)
    s_out = os.path.join(os.path.dirname(out), "outreach_S-AC.tsv")
    write_tsv(s_out, [r[S:] for r in rows], HEADER[S:])
    from collections import Counter
    print(f"{len(rows)} rows -> {out} (A..AC) and {s_out} (S..AC); priority {dict(Counter(r[S + 1] for r in rows))}",
          file=sys.stderr)


if __name__ == "__main__":
    main()

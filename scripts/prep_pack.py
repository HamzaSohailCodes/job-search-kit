#!/usr/bin/env python3
"""Start an interview prep pack from everything already known about one application.

Pulls from the repo (no web): the company file (status, timeline, fit notes, form answers, job description, and
the "My notes" section with feedback from earlier rounds), the exact resume that was sent (pinned PDF text, when
pypdf is installed), the tailored keywords.md if one exists, and the stories file (profile/stories.md). Writes
interview-prep/<company>/pack-<stage>-<date>.md with those facts filled in and the sections Claude completes
(research, likely questions, story map, bridge answers, questions to ask) marked TODO.

Usage:
  python3 scripts/prep_pack.py "<Company>" [--role "<title words>"] [--stage screen|technical|final|other] [--date YYYY-MM-DD]
  Run it with .venv/bin/python (created by ./setup.sh, has pypdf) to include the resume text.
Data location: the repo root, or $JOB_KIT_DATA if set.
"""
import argparse, datetime as dt, glob, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_applications import data_root, dpath, profile, read_text, slug, write_text  # noqa: E402
from core import config  # noqa: E402


def stories_path():
    return dpath("profile", "stories.md")


def find_company_file(company):
    want = slug(company)
    exact = dpath("applications", want + ".md")
    if os.path.exists(exact):
        return exact
    hits = [p for p in glob.glob(dpath("applications", "*.md")) if want in os.path.basename(p)]
    return hits[0] if len(hits) == 1 else None


def sections(md, level):
    """Split markdown into {heading: body} at the given heading level ('## ' or '### ')."""
    out, cur, buf = {}, None, []
    for line in md.splitlines():
        if line.startswith(level) and not line.startswith(level + "#"):
            if cur is not None:
                out[cur] = "\n".join(buf).strip()
            cur, buf = line[len(level):].strip(), []
        elif cur is not None:
            buf.append(line)
    if cur is not None:
        out[cur] = "\n".join(buf).strip()
    return out


def pick_role(roles, role):
    names = [k for k in roles if k not in ("My notes", "Form snapshots not matched to a role")]
    if role:
        names = [k for k in names if role.lower() in k.lower()] or names
    return names[0] if names else None


def field(table, name):
    m = re.search(r"^\| " + re.escape(name) + r" \| (.*?) \|$", table, re.M)
    return m.group(1).strip() if m else ""


def resume_text(block):
    m = re.search(r"Resume pinned:.*?`([^`]+\.pdf)`", block) or re.search(r"Resume uploaded: (\S+\.pdf)", block)
    if not m:
        return "", ""
    rel = m.group(1)
    path = rel if os.path.isabs(rel) else dpath(rel)
    if not os.path.exists(path) and os.path.exists(config.path(rel)):
        path = config.path(rel)
    try:
        from pypdf import PdfReader
        txt = "\n".join(pg.extract_text() or "" for pg in PdfReader(path).pages)
        return rel, txt.strip()
    except Exception as e:  # pypdf missing or file moved
        return rel, f"(could not read the PDF: {type(e).__name__}; open {rel})"


def tailored_keywords(company, title):
    key = slug(company)
    for p in sorted(glob.glob(dpath("resumes", "tailored", "*", "*", "keywords.md")), reverse=True):
        d = os.path.basename(os.path.dirname(p))
        if d.startswith(key) and (not title or any(w in d for w in slug(title).split("-")[:3])):
            return os.path.relpath(p, data_root()), read_text(p)
    return "", ""


_SKIP_LINE = r"@|\bIssued\b|\bValid through\b|·|\|"


def claims(text):
    """Resume lines with a number or a named result: what the interviewer will probe."""
    # drop header and contact lines first, or they glue onto the next sentence and hide it
    kept = [l for l in text.splitlines() if not re.search(_SKIP_LINE, l)]
    flat = re.sub(r"\s+", " ", " ".join(kept))
    out = []
    for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])|\s*[•●▪]\s*", flat):
        s = s.strip(" -\t")
        if len(s) < 50 or re.search(_SKIP_LINE, s):
            continue
        if re.search(r"\d+%|\d+\+|\b\d{2,}\b|doubled|halved|\bcut\b|reduced|increased|replaced", s, re.I):
            out.append(s[:240])
    return out[:12]


def visa_question(p):
    if not config.needs_sponsorship(p):
        return []
    visa = config.get(p, "work_authorization.visa_status", "") or "my visa"
    return [f"- First question to ask if not settled: do you sponsor ({visa})? Use the wording in profile/answer_bank.md."]


def story_headings(path):
    if not os.path.exists(path):
        return []
    skip = {"approved short answers"}
    return [l for l in read_text(path).splitlines()
            if re.match(r"#{2,3} ", l) and l.lstrip("# ").strip().lower() not in skip and "{" not in l]


def build(company, role=None, stage="screen", date=None):
    p = profile()
    path = find_company_file(company)
    if not path:
        raise SystemExit(f"no single applications/*.md matches {company!r}; check the company name")
    md = read_text(path)
    roles = sections(md, "## ")
    name = pick_role(roles, role)
    body = roles.get(name, "")
    sub = sections(body, "### ")
    notes = roles.get("My notes", "")
    rpath, rtext = resume_text(sub.get("What we submitted", ""))
    kpath, ktext = tailored_keywords(company, name)
    fit = re.search(r"\*\*Fit notes.*?\*\*\s*(.*)", body)
    date = date or dt.date.today().isoformat()
    h1 = next((l for l in md.splitlines() if l.startswith("# ")), "")
    title = h1[2:].strip() or company
    root = data_root()
    snap = [f"- Status: {field(body, 'Status')}", f"- Outcome / next step: {field(body, 'Outcome / next step')}"]
    if config.module_on(p, "h1b"):
        snap.append(f"- H-1B evidence: {field(body, 'H-1B evidence')}")
    snap += [f"- Location: {field(body, 'Location')} | Pay posted: {field(body, 'Pay posted')}",
             f"- Fit notes at shortlist time: {fit.group(1).strip() if fit else 'none'}"]
    out = [f"# {title}: {name} ({stage} prep, {date})", "",
           f"Source files: `{os.path.relpath(path, root)}`" + (f", resume `{rpath}`" if rpath else "") + (f", `{kpath}`" if kpath else ""), "",
           "Rule: no claim in the room that isn't on the paper, and every claim on the paper must be defensible in depth.",
           "Gaps get honest bridge answers (acknowledge, closest real experience, how I'd ramp), never invented experience.", "",
           "## Snapshot", ""] + snap + ["",
           "## Timeline and earlier feedback", "", sub.get("Timeline", "_none_"), "",
           (notes if notes else "_No notes from earlier rounds. Ask the candidate what was said in the last call._"), "",
           "## Logistics (ask the candidate what isn't known)", "", "- Date and time:", "- Format (phone, video, onsite, take-home):",
           "- Interviewers (name, title):"] + visa_question(p) + ["",
           "## Consistency brief: claims on the resume that was sent", ""]
    out += [f"- {c}" for c in claims(rtext)] or ["- (resume text not available; read the pinned PDF)"]
    out += ["", "## Tailoring report (keywords, gaps)", "", ktext.strip() if ktext else "_No tailored resume for this role._", "",
            "## Company research (TODO, verified only)", "",
            "Each fact needs a source link from the company's own site or reputable press. Unverified facts stay out.",
            "- What they sell and to whom:", "- Recent news (last 6 months):", "- Team and stack signals:",
            "- 2 to 3 conversation hooks for \"why us\":", "",
            "## Likely questions (TODO)", "",
            "Order: feedback from earlier rounds, then the gaps, then each must-have in the posting, then the stage type.", "",
            "## Story map (TODO)", "",
            "Map each likely question to one story from profile/stories.md. Use a different story per question.", "",
            "## Gaps and bridge answers (TODO)", "", "## Questions to ask (TODO, 4 to 6, none the website already answers)", "",
            "## Job description", "", sub.get("Job description", "_not in the company file_"), "",
            "## Form answers we submitted", "", sub.get("What we submitted", "_none recorded_"), ""]
    heads = story_headings(stories_path())
    if heads:
        out += ["## Stories available (from profile/stories.md)", ""] + heads
    dest = dpath("interview-prep", slug(company), f"pack-{stage}-{date}.md")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    write_text(dest, "\n".join(out) + "\n")
    return dest


def main(argv=None):
    ap = argparse.ArgumentParser(description="Start interview-prep/<company>/pack-<stage>-<date>.md from the company file.")
    ap.add_argument("company"); ap.add_argument("--role")
    ap.add_argument("--stage", default="screen", choices=["screen", "technical", "final", "other"])
    ap.add_argument("--date")
    a = ap.parse_args(argv)
    print(os.path.relpath(build(a.company, a.role, a.stage, a.date), data_root()))
    return 0


if __name__ == "__main__":
    sys.exit(main())

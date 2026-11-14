"""Recruiter first emails (subject + body) for shortlisted C2C roles. Drafts only: nothing is sent.

- The opener names the role and where the candidate applied, plus one line on who they are that
  matches the role family (AI / full-stack / backend / lead).
- Three bullets. Each starts with the JD's own must-have wording, then one proof line from
  c2c.outreach.proof in config/profile.json (lines the candidate wrote from their resume).
  Skills that appear only under "nice to have / preferred" are ignored. Topics without a proof
  line are never claimed; if fewer than three topics have one, a [placeholder] bullet is left to fill.
- No rate, visa or work authorization, location or years-per-skill line. Asks about remote only when
  the JD hints at onsite or hybrid.

Usage (repo root):
  python3 modules/c2c/outreach/build_emails.py --jobs batches/<date>-c2c/shortlist.csv \
      [--raw batches/<date>-c2c/raw_jobs_<date>.json] [--contacts batches/<date>-c2c/contacts_shortlist.csv] \
      [--out batches/<date>-c2c/emails.tsv]

--raw defaults to the newest raw_jobs_*.json next to --jobs (job descriptions come from it).
--contacts is contacts.py output (Link, Apply email; an optional "First name" column wins over the guess).
Output TSV: Link, To, Email kind, Email subject, Email body (subject/body go in the tracker's X:Y,
Email Subject / Email Body; build_outreach.py writes whole rows).

Config read (all optional except identity.full_name):
  c2c.outreach.proof     {topic: "proof line"} or {topic: {"proof", "patterns", "weight", "subject_keys", "label"}}
                         Built-in topics: rag agents llm evals docai react node graphql python sql aws azure health lead.
                         A new topic needs "patterns" (regexes of JD phrases).
  c2c.outreach.openers   {family: "I'm a ..."} for ai, ai_lead, lead, backend, fullstack
  c2c.outreach.closing   last line before the signature ("" = the built-in line)
"""
import argparse
import csv
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_d = HERE
while not os.path.exists(os.path.join(_d, "core", "config.py")) and _d != os.path.dirname(_d):
    _d = os.path.dirname(_d)
sys.path.insert(0, _d)
from core import config  # noqa: E402

csv.field_size_limit(10**8)
MODULE_OFF = ("The contract search is off: no contract work type is selected. Add a contract type with "
              "/setup → update my profile (targets.employment_types).")

# topic: (JD phrases, weight). The proof line for each topic comes from config.
PATTERNS = {
    "rag": ([r"Retrieval[- ]Augmented Generation(?: \(RAG\))?", r"\bRAG\b", r"vector (?:databases?|search|stores?)",
             r"embeddings?", r"semantic search", r"hybrid search"], 1.0),
    "agents": ([r"multi[- ]agent(?: systems| orchestration| workflows)?", r"agentic (?:AI|workflows?|systems?)", r"AI agents?",
                r"LLM agents?", r"tool[- ]calling", r"function calling", r"LangGraph", r"\bMCP\b", r"Model Context Protocol"], 1.0),
    "llm": ([r"Large Language Models?(?: \(LLMs?\))?", r"\bLLMs?\b", r"Generative AI", r"\bGenAI\b", r"Gen AI", r"OpenAI",
             r"prompt engineering", r"LangChain"], 0.6),
    "evals": ([r"evals?\b", r"evaluation (?:frameworks?|suites?|pipelines?|metrics)", r"groundedness", r"LLM observability",
               r"Langfuse", r"guardrails?"], 1.0),
    "docai": ([r"\bOCR\b", r"document (?:processing|extraction|understanding|intelligence|AI)", r"intelligent document processing"], 1.0),
    "react": ([r"React(?:\.js|JS)?\b", r"Next\.?js", r"TypeScript", r"Redux", r"front[- ]?end"], 0.9),
    "node": ([r"Node\.?js", r"NestJS", r"Express(?:\.js)?", r"RESTful APIs?", r"REST APIs?"], 0.9),
    "graphql": ([r"GraphQL", r"MongoDB", r"microservices?(?: architecture)?", r"distributed systems"], 1.0),
    "python": ([r"Python", r"FastAPI", r"Flask", r"Pydantic", r"Django"], 0.9),
    "sql": ([r"PostgreSQL", r"Postgres", r"SQL Server|MSSQL", r"\bSQL\b", r"Redis", r"data model(?:ing|s)?"], 0.8),
    "aws": ([r"\bAWS\b", r"Amazon Web Services"], 0.8),
    "azure": ([r"Azure", r"Kafka", r"event[- ]driven(?: architecture)?", r"webhooks?"], 1.0),
    "health": ([r"HIPAA", r"FHIR", r"HL7", r"healthcare", r"clinical"], 1.0),
    "lead": ([r"technical leadership", r"tech(?:nical)? lead", r"mentor(?:ing|ship)?", r"lead (?:a |the )?(?:team|engineers)",
              r"solutions? architect(?:ure)?", r"system design"], 0.8),
}
FALLBACK = {"ai": ["llm", "agents", "rag"], "fullstack": ["react", "node", "python"],
            "backend": ["python", "node", "sql"], "lead": ["lead", "graphql", "llm"]}
LABEL_DEFAULT = {"rag": "RAG", "agents": "AI agents", "llm": "LLMs", "evals": "LLM evaluation", "docai": "Document AI",
                 "react": "React", "node": "Node.js", "graphql": "Microservices", "python": "Python", "sql": "PostgreSQL",
                 "aws": "AWS", "azure": "Azure / event-driven integrations", "health": "Healthcare",
                 "lead": "Technical leadership"}
# Short subject keyword per topic; the JD's own term wins when it uses one of these.
SUBJECT_KEY = {"rag": ["RAG"], "agents": ["LangGraph", "MCP", "Agentic AI", "AI Agents"], "llm": ["LLMs", "GenAI"],
               "evals": ["LLM Evals"], "docai": ["OCR"], "react": ["React", "Next.js", "TypeScript"],
               "node": ["Node.js", "NestJS"], "graphql": ["GraphQL", "Microservices"], "python": ["FastAPI", "Python"],
               "sql": ["PostgreSQL", "SQL"], "aws": ["AWS"], "azure": ["Azure", "Kafka"], "health": ["FHIR", "HIPAA"],
               "lead": ["Tech Lead"]}
FAMILY_DESC = {"ai": "AI engineer", "ai_lead": "AI engineer with technical-lead experience",
               "lead": "technical lead and full-stack engineer", "backend": "backend engineer",
               "fullstack": "full-stack engineer"}
PLACEHOLDER = "[add one proof line from profile/master_cv.md]"

NICE = re.compile(r"(nice[- ]to[- ]have|good[- ]to[- ]have|preferred (?:qualifications|skills)|bonus points?|\bplus(?:es)?:|desired skills)", re.I)
ONSITE = re.compile(r"on-?site|hybrid|in[- ]office|days? (?:a|per) week|\blocal (?:candidates|to)\b|relocat|f2f|face to face|in person", re.I)
GENERIC_INBOX = {"jobs", "job", "careers", "career", "hr", "info", "resumes", "resume", "recruiting", "recruitment",
                 "positions", "hiring", "talent", "apply", "staffing", "admin", "contact", "sales", "team", "usjobs",
                 "itjobs", "req", "reqs", "submissions", "bench", "hotlist", "recruiter", "recruiters", "consultants"}


# --- catalog from config -----------------------------------------------------------

def catalog(p):
    """{topic: (patterns, proof, weight, subject_keys, label)} for topics the candidate has a proof line for."""
    out = {}
    for topic, v in (config.get(p, "c2c.outreach.proof") or {}).items():
        v = {"proof": v} if isinstance(v, str) else dict(v or {})
        proof = (v.get("proof") or "").strip().rstrip(".")
        base_pats, base_w = PATTERNS.get(topic, ([], 1.0))
        pats = v.get("patterns") or base_pats
        if not proof or not pats:
            continue
        out[topic] = (pats, proof, float(v.get("weight", base_w)),
                      v.get("subject_keys") or SUBJECT_KEY.get(topic) or [v.get("label") or topic],
                      v.get("label") or LABEL_DEFAULT.get(topic) or topic)
    return out


def opener(p, fam):
    custom = (config.get(p, "c2c.outreach.openers") or {}).get(fam)
    if custom:
        return custom.strip()
    level = (config.get(p, "current_role.level") or "").lower()
    lvl = f"{level} " if level in ("senior", "lead", "staff", "principal") else ""
    company = config.get(p, "current_role.company", "")
    art = "an" if (lvl or FAMILY_DESC[fam])[0].lower() in "aeiou" else "a"
    return f"I'm {art} {lvl}{FAMILY_DESC[fam]}" + (f", currently at {company}." if company else ".")


def signature(p):
    li = re.sub(r"^https?://(www\.)?", "", config.get(p, "identity.linkedin", "") or "").rstrip("/")
    tail = " · ".join(x for x in [config.get(p, "identity.phone", ""), li] if x)
    return "Thanks,\n" + config.full_name(p) + (f"\n{tail}" if tail else "")


# --- text helpers (unchanged from the original builder) ----------------------------

def family(title):
    t = title.lower()
    ai = re.search(r"\b(ai|ml|llm|genai|gen ai|generative|agentic|machine learning|nlp)\b", t)
    lead = re.search(r"\b(lead|architect|principal|head)\b", t)
    if ai:
        return "ai_lead" if lead else "ai"
    if lead:
        return "lead"
    if re.search(r"python|backend|back-end|data|etl|automation", t) and not re.search(r"full|react|front", t):
        return "backend"
    return "fullstack"


def must_text(desc):
    m = NICE.search(desc)
    return desc[:m.start()] if m else desc


def _words(x):
    return {w[:4] for w in re.findall(r"[a-z]+", x.lower()) if len(w) > 2}


def make_label(found):
    """Most descriptive JD phrase first; add a second only if it says something different."""
    ranked = sorted(found, key=len, reverse=True)
    label = ranked[0]
    for other in ranked[1:]:
        initials = "".join(w[0] for w in re.findall(r"[A-Za-z]+", label)).lower()
        same = (_words(other) & _words(label)) or other.lower() in label.lower() or other.lower() == initials
        if not same and len(label) + len(other) < 45:
            return f"{label} / {other}"
    return label


def tidy(label):
    label = re.sub(r"\s+", " ", label)
    if re.search(r"\bevals?\b", label, re.I) and "evaluation" not in label.lower():
        label = re.sub(r"\bevals?\b", "evaluation", label, flags=re.I)
    if label.lower() == "evaluation":
        label = "LLM evaluation"
    return label[0].upper() + label[1:] if label and label[0].islower() else label


def short(t, n=60):
    """The role name as a recruiter would say it, without location, years or long skill lists."""
    t = re.sub(r"\(.*?\)", "", t)
    t = re.sub(r"--.*$|\s+-\s*(remote|100% remote).*$|\s*-?\s*F2F.*$|\s*-\s*\d+\+.*$|\s+remote\s*$|\s*#\S+.*$", "", t, flags=re.I)
    head = t.split("/")[0].strip()
    if "/" in t and len(head.split()) >= 2 and re.search(r"(engineer|developer|architect)\s*$", head, re.I):
        t = head
    if len(t) > 45:
        m = re.match(r"^(.*?\b(engineer|developer|architect))\b", t, re.I)
        if m:
            t = m.group(1)
    t = re.sub(r"\s+", " ", t).strip(" -/,;:")
    t = re.sub(r"\bAi\b", "AI", t)
    if t.isupper():
        t = t.split(" - ")[0]
        t = " ".join(w if w in ("AI", "LLM", "ML", "API", "AWS") else w.capitalize() for w in t.split())
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0]


# --- picking and composing ---------------------------------------------------------

def pick(title, desc, fam, cat):
    """Up to three (score, topic, label, proof): JD must-haves the candidate has proof for, then
    the family fallbacks they have proof for, then placeholders named after the JD's topics."""
    must = must_text(desc)
    L = max(len(must), 1)
    scored, unproven = [], []
    topics = dict(PATTERNS)
    for t, v in cat.items():
        topics[t] = (v[0], v[2])
    for topic, (pats, w) in topics.items():
        found, first, n_title = [], L, 0
        for pt in pats:
            for m in re.finditer(pt, must, re.I):
                s = m.group(0).strip()
                if s.lower() not in [f.lower() for f in found]:
                    found.append(s)
                first = min(first, m.start())
            n_title += len(re.findall(pt, title, re.I))
        n = sum(len(re.findall(pt, must, re.I)) for pt in pats)
        if not n and not n_title:
            continue
        score = (n_title * 3 + min(n, 6) + (1 - first / L) * 2) * w
        label = make_label(found) if found else re.search("|".join(pats), title, re.I).group(0)
        if topic in cat:
            scored.append((score, topic, label, cat[topic][1]))
        else:
            unproven.append((score, topic, label, PLACEHOLDER))
    scored.sort(key=lambda x: -x[0])
    chosen = scored[:3]
    for topic in FALLBACK["ai" if fam.startswith("ai") else fam]:
        if len(chosen) >= 3:
            break
        if topic in cat and topic not in [c[1] for c in chosen]:
            chosen.append((0, topic, None, cat[topic][1]))
    for extra in sorted(unproven, key=lambda x: -x[0]):
        if len(chosen) >= 3:
            break
        chosen.append(extra)
    return chosen


def subject(p, t, chosen, desc, cat):
    keys = []
    for _, tp, _, proof in chosen:
        if proof == PLACEHOLDER:
            continue
        opts = cat[tp][3] if tp in cat else SUBJECT_KEY.get(tp, [])
        if not opts:
            continue
        k = next((o for o in opts if re.search(r"\b" + re.escape(o) + r"\b", desc, re.I)), opts[-1])
        if k.lower() not in t.lower() and k not in keys:
            keys.append(k)
    base = f"{t} – {config.full_name(p)}"
    while keys and len(base) + 3 + len(", ".join(keys)) > 85:
        keys.pop()
    return base + (" | " + ", ".join(keys) if keys else "")


def email_kind(email):
    if not email:
        return ""
    local = re.split(r"[._\-+0-9]", email.split("@")[0])[0].lower()
    return "ATS inbox" if (local in GENERIC_INBOX or len(local) <= 2) else "Recruiter (named)"


def first_name(email, given=""):
    """Only when certain: a name given in the contacts file, or first.last@ / first_last@ style."""
    if given.strip():
        return given.strip().split()[0].capitalize()
    if email_kind(email) != "Recruiter (named)":
        return ""
    local = email.split("@")[0]
    parts = re.split(r"[._\-]", local)
    if len(parts) >= 2 and parts[0].isalpha() and len(parts[0]) > 2 and parts[0].lower() not in GENERIC_INBOX:
        return parts[0].capitalize()
    return ""


def where(source):
    s = (source or "").lower()
    return "on Dice" if s.startswith("dice") else "on LinkedIn" if s.startswith("linkedin") else "through your site"


def compose(p, title, desc, source="dice", fname=""):
    """Return (subject, body, chosen) for one role."""
    cat = catalog(p)
    fam = family(title)
    t = short(title)
    chosen = pick(title, desc, fam, cat)
    bullets = [f"• {tidy(lab or LABEL_DEFAULT.get(tp, tp))}: {proof}." for _, tp, lab, proof in chosen]
    closing = config.get(p, "c2c.outreach.closing") or "I'm free most afternoons this week for a quick call. Resume attached."
    body = (f"Hi {fname or 'there'},\n\n"
            f"I applied {where(source)} for your {t} role. {opener(p, fam)} Here's how I match what you're looking for:\n\n"
            + "\n".join(bullets) + "\n\n"
            + ("Is this fully remote, or is some onsite time expected?\n\n" if ONSITE.search(desc) else "")
            + closing + "\n\n" + signature(p))
    return subject(p, t, chosen, desc, cat), body, chosen


def read_rows(path):
    with open(path, newline="") as f:
        head = f.readline()
        f.seek(0)
        return list(csv.DictReader(f, delimiter="\t" if "\t" in head else ","))


def load_descriptions(jobs_path, raw_path=None):
    if not raw_path:
        found = sorted(glob.glob(os.path.join(os.path.dirname(os.path.abspath(jobs_path)), "raw_jobs_*.json")))
        raw_path = found[-1] if found else None
    if not raw_path or not os.path.exists(raw_path):
        return {}
    with open(raw_path) as f:
        return {j["url"].split("?")[0]: j.get("description", "") or "" for j in json.load(f)}


def load_contacts(path):
    if not path:
        return {}
    return {r.get("Link", "").split("?")[0]: r for r in read_rows(path)}


def cell(s):
    s = str(s)
    return '"' + s.replace('"', '""') + '"' if any(c in s for c in '\n\t"') else s


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", required=True)
    ap.add_argument("--raw")
    ap.add_argument("--contacts")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    p = config.load()
    if not config.module_on(p, "c2c"):
        sys.exit(MODULE_OFF)
    if not catalog(p):
        print("Warning: c2c.outreach.proof is empty in config/profile.json; every bullet is a placeholder.",
              file=sys.stderr)
    descs = load_descriptions(a.jobs, a.raw)
    contacts = load_contacts(a.contacts)
    out = a.out or os.path.join(os.path.dirname(os.path.abspath(a.jobs)), "emails.tsv")
    lines, placeholders = ["\t".join(["Link", "To", "Email kind", "Email subject", "Email body"])], 0
    for r in read_rows(a.jobs):
        link = r.get("Link", "").split("?")[0]
        c = contacts.get(link, {})
        to = c.get("Apply email", "")
        fn = first_name(to, c.get("First name", ""))
        subj, body, _ = compose(p, r.get("Title", ""), descs.get(link, ""), r.get("Source", ""), fn)
        placeholders += PLACEHOLDER in body
        lines.append("\t".join(cell(x) for x in [link, to, email_kind(to), subj, body]))
    with open(out, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"{len(lines) - 1} drafts written to {out}; {placeholders} still have a placeholder bullet", file=sys.stderr)


if __name__ == "__main__":
    main()

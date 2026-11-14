#!/usr/bin/env python3
"""Match one job posting against the candidate's resume content and pick/reorder a base version.

Facts come only from profile/resume_content.json (the engine's data) and profile/skills_inventory.md.
For each job it:
  1. pulls the key requirements (requirement-style lines) from the posting,
  2. finds the posting's tech keywords, split into ones the candidate has (MATCHED) and ones they don't (GAPS),
  3. picks the closest base version (by each version's "match" terms and "title_regex") and reorders skill
     lines, skill terms, bullets and projects so the matched keywords come first; the headline names the top
     matched keywords,
  4. (CLI) writes <out>/<key>/<First_Last>_Resume.{html,tex,pdf} and keywords.md.
Nothing is added that isn't already in the content; gaps are reported, never inserted.
tailor_batch.py builds on this with the full 70/30 pass and the checks; use that for real batches.

Usage (repo root): .venv/bin/python .claude/skills/build-batch-resume/scripts/tailor.py --jobs jobs.json --out DIR
jobs.json: [{"key": "acme-senior-engineer", "company": "Acme", "title": "Senior Engineer", "desc": "...", "url": "..."}]
"""
import argparse
import copy
import json
import os
import re
import sys

_d = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _d)
while not os.path.exists(os.path.join(_d, "core", "config.py")) and _d != os.path.dirname(_d):
    _d = os.path.dirname(_d)
sys.path.insert(0, _d)
from core import config  # noqa: E402
from resume import engine  # noqa: E402
import catalog as K  # noqa: E402

GENERIC = K.CONCEPT | {"Langfuse", "OCR", "webhooks", "RBAC", "TDD", "Git", "SQL", "JavaScript"}


# ---------- skills inventory (profile/skills_inventory.md) ----------

def inventory_path():
    return os.environ.get("JOB_KIT_SKILLS_INVENTORY") or config.path("profile", "skills_inventory.md")


def read_inventory(path=None):
    """{"used": [(tool, where)], "familiar": [(tool, note)], "never": [tool]} from the inventory's three sections.

    "used" = used but not on the base resume (Skills line + one bullet/stack mention under `where`);
    "familiar" = Skills line at most (the 70/30 pass never adds these); "never" = never claim, always a gap."""
    path = path or inventory_path()
    out = {"used": [], "familiar": [], "never": []}
    if not os.path.exists(path):
        return out
    sec = None
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    for line in lines:
        s = line.strip()
        if s.startswith("#"):
            h = s.lower()
            sec = "familiar" if "familiar" in h else "never" if "never" in h else "used" if "used" in h else None
            continue
        if not sec or "{" in s:
            continue  # template placeholders
        if sec == "never" and s.startswith(("- ", "* ")):
            out["never"].append(s[2:].strip())
            continue
        m = re.match(r"\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|", s)
        if m and sec in ("used", "familiar") and not re.fullmatch(r"[-: ]+", m.group(1)) and m.group(1).lower() != "tool":
            out[sec].append((m.group(1), m.group(2)))
    return out


# ---------- the candidate's keyword table ----------

def auto_regex(name):
    """'ECS / EKS' -> word-bounded alternatives; '(...)' parts become alternatives too."""
    alts = [a.strip() for a in re.split(r"\s*/\s*|\s*[(),]\s*", name) if len(a.strip()) > 1]
    return "|".join(r"(?<![\w.])" + re.escape(a) + r"(?![\w])" for a in alts) or re.escape(name)


def catalog_term_for(name):
    """The catalog term a tool name refers to (longest regex hit), or None."""
    best, blen = None, 0
    for term, (rx, _) in K.CATALOG.items():
        m = re.search(rx, name, re.I)
        if m and len(m.group(0)) > blen:
            best, blen = term, len(m.group(0))
    return best


def candidate_terms(R, inv=None):
    """{term: {"rx", "category", "source"}} for everything the candidate can honestly be matched on.

    Tools count when they are on a Skills line, a Stack line or the inventory's "used" table; concepts count when
    they appear anywhere in the resume content. keyword_aliases in resume_content.json override any regex."""
    inv = inv if inv is not None else read_inventory()
    aliases = R.get("aliases", {})
    items = [it for g in R["skills"].values() for it in g["items"]]
    stacks = [x.strip() for j in R["jobs"].values() for x in re.split(r",(?![^()]*\))", engine.plain(j["stack"])) if x.strip()]
    tool_text = engine.plain(" , ".join(items + stacks))
    all_text = " ".join([tool_text] + [engine.resume_text(R, v) for v in R["versions"].values()])
    terms = {}
    for term, (rx, cat) in K.CATALOG.items():
        rx = aliases.get(term, rx)
        if re.search(rx, all_text if cat == "concept" else tool_text, re.I):
            terms[term] = {"rx": rx, "category": cat, "source": "content"}
    for tool, where in inv["used"]:
        ct = catalog_term_for(tool)
        rx = aliases.get(tool) or (K.CATALOG[ct][0] if ct else auto_regex(tool))
        cat = K.CATALOG[ct][1] if ct else ""
        terms.setdefault(ct or tool, {"rx": rx, "category": cat, "source": "inventory"})
        if terms[ct or tool]["source"] == "inventory":
            terms[ct or tool].update(tool=tool, where=where)
    for it in items + stacks:
        it_plain = engine.plain(it)
        if not it_plain or any(re.search(t["rx"], it_plain, re.I) for t in terms.values()):
            continue
        name = re.sub(r"\s*\(.*?\)", "", it_plain).strip()
        if len(name) > 1:
            terms[name] = {"rx": aliases.get(name, auto_regex(name)), "category": "",
                           "source": "skill-item", "generic": not name[:1].isupper()}
    for term, rx in aliases.items():
        terms.setdefault(term, {"rx": rx, "category": "", "source": "alias"})
    return terms


def is_generic(term, terms):
    return term in GENERIC or terms.get(term, {}).get("generic", False)


def found(terms, text):
    return [k for k, t in terms.items() if re.search(t["rx"], text, re.I)]


def gap_terms(terms, inv):
    """Catalog terms the candidate does not have, plus the inventory's never-claim list."""
    gaps = {k: rx for k, (rx, _) in K.CATALOG.items() if k not in terms}
    for t in inv["never"]:
        ct = catalog_term_for(t)
        if ct and ct not in terms:
            gaps[ct] = K.CATALOG[ct][0]
        elif not ct:
            gaps[t] = auto_regex(t)
    familiar = {t: (K.CATALOG[catalog_term_for(t)][0] if catalog_term_for(t) else auto_regex(t))
                for t, _ in inv["familiar"]}
    for t in familiar:
        gaps.pop(catalog_term_for(t) or t, None)
    return gaps, familiar


# ---------- the posting ----------

REQ_HEAD = re.compile(r"requirement|qualification|what you.?ll (bring|need)|you (have|bring|are|might be)|about you|who you are|"
                      r"must have|looking for|ideal candidate|skills|experience|nice to have|bonus|preferred", re.I)
REQ_LINE = re.compile(r"\d\+? ?years|experience|proficien|strong|deep|familiar|expert|built|shipped|knowledge|comfortable|"
                      r"ability|track record", re.I)


def key_requirements(desc, n=8):
    lines = [l.strip(" \t-*•·").strip() for l in re.split(r"[\n\r]+|(?<=\.)\s+(?=[A-Z])|\s[•·]\s", desc)]
    lines = [re.sub(r"\*+|_{2,}", "", l).strip() for l in lines]
    lines = [l for l in lines if 25 <= len(l) <= 260 and not re.search(
        r"screen|interview|minutes|onsite day|benefit|401k|equity|salary|visa", l, re.I)]
    out, in_req = [], False
    for l in lines:
        if REQ_HEAD.search(l) and len(l) < 60:
            in_req = True
            continue
        if (in_req or REQ_LINE.search(l)) and REQ_LINE.search(l) and l not in out:
            out.append(l)
    return out[:n]


def score_text(text, kws, terms):
    t = engine.plain(text)
    return sum(1 for k in kws if re.search(terms[k]["rx"], t, re.I))


def pick_version(R, job, have, terms):
    title = job["title"]
    names = [R["default_version"]] + [k for k in R["versions"] if k != R["default_version"]]
    scores = {}
    for name in names:
        v = R["versions"][name]
        s = sum(2 if re.search(terms[k]["rx"], title, re.I) else 1 for k in v.get("match", []) if k in have)
        if v.get("title_regex") and re.search(v["title_regex"], title, re.I):
            s += int(v.get("title_boost", 4))
        scores[name] = s
    return max(names, key=lambda n: scores[n]), scores


def tailor(R, job, terms, inv=None):
    """Returns (v, R2, base, have, gaps): R2 is a copy of R with skill terms reordered; v the reordered version."""
    inv = inv if inv is not None else read_inventory()
    desc = job["desc"]
    have = found(terms, desc + " " + job["title"])
    gaps_tbl, _ = gap_terms(terms, inv)
    gaps = [k for k, rx in gaps_tbl.items() if re.search(rx, desc + " " + job["title"], re.I)]
    base, _ = pick_version(R, job, have, terms)
    v = engine.version(R, base)
    R2 = copy.deepcopy(R)

    # skill lines: most matched first (the first line stays on top), terms inside each line reordered
    ids = [k for k in v["skills"] if isinstance(k, str) and k in R2["skills"]]
    for k in ids:
        R2["skills"][k]["items"].sort(key=lambda it: -score_text(it, have, terms))
    if ids:
        v["skills"] = [ids[0]] + sorted(ids[1:], key=lambda k: -score_text(", ".join(R2["skills"][k]["items"]), have, terms))
    # bullets inside each job and projects: most matched first (stable)
    for j, bl in v["jobs"].items():
        v["jobs"][j] = sorted(bl, key=lambda b: -score_text(R["bullets"].get(b, b), have, terms))
    v["projects"] = sorted(v["projects"], key=lambda p: -score_text(" ".join(R["projects"][p]["bullets"]), have, terms)
                           if isinstance(p, str) and p in R["projects"] else 0)

    top = [k for k in sorted(have, key=lambda k: -len(re.findall(terms[k]["rx"], desc, re.I)))
           if not is_generic(k, terms) and k not in K.NO_HEADLINE][:4]
    head = v.get("headline_base") or v.get("headline", "").split(" · ")[0]
    v["headline"] = head + (" · " + " · ".join(top) if top else "")
    return v, R2, base, have, gaps


def write(R, job, out, terms, inv):
    from resume.build import build_one
    v, R2, base, have, gaps = tailor(R, job, terms, inv)
    d = os.path.join(out, job["key"])
    os.makedirs(d, exist_ok=True)
    build_one(R2, v, os.path.join(d, f"{engine.file_stem()}_Resume"), {"html", "pdf"})
    reqs = key_requirements(job["desc"])
    with open(os.path.join(d, "keywords.md"), "w", encoding="utf-8") as f:
        f.write(f"# {job['company']}: {job['title']}\n\n{job.get('url', '')}\n\nBase version: {base}\n\n"
                f"Headline: {engine.plain(v['headline'])}\n\n## Key requirements from the posting\n" +
                "".join(f"- {r}\n" for r in reqs) +
                "\n## Keywords you match (moved to the top of the resume)\n" + ", ".join(have) +
                "\n\n## Gaps (asked for, not on your resume; not added)\n" + (", ".join(gaps) or "none found") + "\n")
    return dict(key=job["key"], base=base, matched=have, gaps=gaps, reqs=reqs, dir=d)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    R = engine.load_content()
    inv = read_inventory()
    terms = candidate_terms(R, inv)
    res = [write(R, j, a.out, terms, inv) for j in json.load(open(a.jobs, encoding="utf-8"))]
    json.dump(res, open(os.path.join(a.out, "tailor_summary.json"), "w"), indent=1)
    for r in res:
        print(f"{r['key']}: {r['base']} | {len(r['matched'])} matched | gaps: {', '.join(r['gaps']) or '-'}")

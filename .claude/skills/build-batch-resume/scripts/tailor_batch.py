#!/usr/bin/env python3
"""Build one tailored resume per job with the 70/30 rule.

70% CORE, never changed per job: every bullet's text, every base skill term, the summary body, jobs, dates,
education, certifications (all from profile/resume_content.json).

30% TUNED per job:
  1. headline = the posting's title (Staff/Principal/Manager/Director titles fall back to the base headline)
     plus the top 3 matched keywords;
  2. base version (versions in resume_content.json) and the order of skill lines, terms and bullets (tailor.py);
  3. spelling mirrored from the posting (ReactJS vs React, Postgres vs PostgreSQL, NodeJS vs Node.js...);
  4. acronyms spelled out once when the posting uses the long form;
  5. up to 4 tools from profile/skills_inventory.md's "used" table that the posting asks for: added to the Skills
     line and to the Stack line of the job where the candidate used them. "Familiar" and "never claim" tools never.
  6. optional per-job overrides written by Claude: {"<key>": {"summary_lead": "...", "headline": "...",
     "reorder": [[x, y]], "swap": [[x, y]]}}. summary_lead replaces only the summary's first sentence.

Checks per resume: core share (words shared with the untailored base version, target >= 70%), keyword counts
(target 2-3 mentions, warn on 1 or 5+), requirement -> evidence bullet map, PDF parse check (pypdf), and
ai-job-search's checks (resume/verify_pdf.py: page count, ASCII dates, literal email and phone;
resume/verify_layout.py: holes, orphaned job titles, thin last page).

The PDF is LaTeX (Tectonic) via resume/latex.py, fitted to `resume_build.pages` (default 2) by tightening spacing
step by step. HTML and DOCX are written too (HTML for the text checks, DOCX for forms that want Word).
--engine chrome falls back to headless Chrome.

Usage (repo root): .venv/bin/python .claude/skills/build-batch-resume/scripts/tailor_batch.py \
    --jobs jobs.json --out resumes/tailored/<date> [--overrides o.json] [--only k1,k2] [--engine latex|chrome]
"""
import argparse
import collections
import csv
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tailor as T  # noqa: E402  (bootstraps the repo root onto sys.path)
import catalog as K  # noqa: E402
from core import config  # noqa: E402
from resume import engine, latex  # noqa: E402
from resume.build import build_one  # noqa: E402

RESUME_DIR = config.path("resume")
MAX_ADDED = 4
CORE_TARGET = 0.70
MAX_BOOST = 5
SENIOR_FALLBACK = re.compile(r"\b(staff|principal|manager|director|head of|vp)\b", re.I)


def count_rx(k, terms=None):
    if k in K.COUNT_RX:
        return K.COUNT_RX[k]
    return r"(?<![\w.])" + re.escape(k) + r"(?![\w])"


def clean_title(t, company=""):
    t = re.sub(r"^Sr\.?\s", "Senior ", t.strip())
    t = re.split(r"\s+[—–|]\s+|\s+-\s+(?=[A-Z])", t)[0]
    t = re.sub(r"\s*\((?![^)]*(stack|end))[^)]*\)", "", t, flags=re.I)  # drop team names in brackets
    t = re.sub(r",?\s*\(([^)]*)\)", r", \1", t)                    # keep (Fullstack/Frontend) as ", Fullstack/Frontend"
    t = re.sub(r"(?<=[a-z])-(?=[A-Z]{2})", ", ", t)                  # Engineer-AI Enabled -> Engineer, AI Enabled
    if company:
        t = re.sub(r",\s*" + re.escape(company) + r"\s*$", "", t, flags=re.I)
    head, _, tail = t.partition(",")
    if tail and len(head.split()) >= 2 and not re.search(
            r"full[- ]?stack|front|back|\bai\b|\bml\b|platform|data|infra|mobile|web|applied|product", tail, re.I):
        t = head                                                  # ", Growth" / ", Payments" are team names, not titles
    return re.sub(r",\s*,", ",", t).strip(" ,")


def spelling_map(desc):
    out = {}
    for res, variants in K.SPELL.items():
        best, n = None, len(re.findall(re.escape(res), desc, re.I))
        for var, rx in variants:
            c = len(re.findall(rx, desc, re.I))
            if c > n:
                best, n = var, c
        if best:
            out[res] = best
    return out


def respell(text, smap):
    for res, var in smap.items():
        text = re.sub(r"(?<![\w.])" + re.escape(res) + K.SPELL_GUARD.get(res, "") + r"(?![\w])", var, text)
    return text


def skills_group_for(R, v, category):
    """The skills group an inventory tool joins: same category in this version, then anywhere, then the last line."""
    ids = [k for k in v["skills"] if isinstance(k, str) and k in R["skills"]]
    for pool in (ids, list(R["skills"])):
        for k in pool:
            if category and R["skills"][k].get("category") == category:
                return k
    return ids[-1] if ids else None


def inventory_added(job, terms):
    """Inventory tools the posting asks for (honest placements only), at most MAX_ADDED."""
    desc, added = job["desc"], []
    for term, t in terms.items():
        if t["source"] != "inventory":
            continue
        m = re.search(t["rx"], desc, re.I)
        first = t["tool"].split()[0].lower()
        if m and len(first) > 2 and re.search(r"\b" + re.escape(first) + r"\b", job.get("company", "").lower()):
            m = None                                              # the company's own name, not a requirement
        if m:
            sent = re.split(r"(?<=[.!?])\s+", desc[max(0, m.start() - 200):m.end() + 50])
            ctx = next((x for x in sent if re.search(t["rx"], x, re.I)), "")
            if re.search(r"customers? (include|like)|clients (include|like)|trusted by|used by|partners (include|like)", ctx, re.I):
                m = None                                          # a customer list, not a requirement
        if m and len(added) < MAX_ADDED:
            added.append((term, t["where"], t["category"], t["tool"]))
    return added


def tailor_one(R, job, terms, inv, ov):
    desc = job["desc"]
    v, R2, base, have, gaps = T.tailor(R, job, terms, inv)
    base_v = engine.version(R, base)
    smap = spelling_map(desc)

    # 5. inventory tools the posting asks for: Skills line + the existing Stack line of the job where used
    added = inventory_added(job, terms)
    for term, where, cat, spelled in added:
        g = skills_group_for(R2, v, cat)
        if g:
            R2["skills"][g]["items"].insert(0, engine.inline(spelled))
            if g not in v["skills"]:
                v["skills"].append(g)
        if where in R2["jobs"] and R2["jobs"][where]["stack"]:
            R2["jobs"][where]["stack"] += ", " + engine.inline(spelled)   # bullets stay fixed

    # 4. acronyms spelled out once (Skills line) when the posting uses the long form
    expanded = []
    for ac, (rx, longf) in K.ACRONYM.items():
        if re.search(rx, desc, re.I):
            for k in v["skills"]:
                items = R2["skills"].get(k, {}).get("items", []) if isinstance(k, str) else []
                hit = next((i for i, it in enumerate(items) if re.search(r"(?<![\w/])" + re.escape(ac) + r"(?![\w])", it)), None)
                if hit is not None:
                    items[hit] = re.sub(r"(?<![\w/])" + re.escape(ac) + r"(?![\w])", longf, items[hit], count=1)
                    expanded.append(ac)
                    break

    # 1. headline: posting title + top matched keywords; summary lead and reviewer edits from overrides
    o = ov.get(job["key"], {})
    title = clean_title(job["title"], job.get("company", ""))
    top = [k for k in sorted(have, key=lambda k: -len(re.findall(terms[k]["rx"], desc, re.I)))
           if not T.is_generic(k, terms) and k not in K.NO_HEADLINE][:3]
    if o.get("headline"):
        v["headline"] = engine.inline(o["headline"])
    elif not SENIOR_FALLBACK.search(title) and 8 <= len(title) <= 70:
        v["headline"] = engine.inline(title) + (" · " + " · ".join(top) if top else "")
    if o.get("summary_lead"):
        rest = re.split(r"(?<=\.)\s+(?=[A-Z])", v["summary"], maxsplit=1)
        v["summary"] = engine.inline(o["summary_lead"].strip()) + (" " + rest[1] if len(rest) > 1 else "")
    # swap: [["x", "y"]] puts existing bullet x in place of bullet y; reorder: [["x", "y"]] puts x directly above y
    for x, y in o.get("swap", []):
        for lst in v["jobs"].values():
            if y in lst and x not in lst and x in R["bullets"]:
                lst[lst.index(y)] = x
    for x, y in o.get("reorder", []):
        for lst in list(v["jobs"].values()) + [v["projects"]]:
            if x in lst and y in lst:
                lst.remove(x)
                lst.insert(lst.index(y), x)

    # 3b. summary closer: posting must-haves already on the Skills lines that would appear only once get one more
    #     honest mention, so each sits in Skills + summary/experience (2-3 total)
    body = engine.resume_text(R2, v)
    sk_terms = [engine.plain(it) for k in v["skills"] if isinstance(k, str) and k in R2["skills"] for it in R2["skills"][k]["items"]]
    ranked = sorted(have, key=lambda k: -len(re.findall(terms[k]["rx"], desc, re.I)))
    boost = []
    for k in ranked:
        if T.is_generic(k, terms) or len(boost) >= MAX_BOOST:
            continue
        term = next((x for x in sk_terms if re.search(count_rx(k), x, re.I)), None)
        if term and len(re.findall(count_rx(k), body, re.I)) < 2:
            term = K.DISPLAY.get(k, re.sub(r"\s*\((Certified|certified)\)", "", term))
            if term not in boost:
                boost.append(term)
    for _, _, _, spelled in added:
        if len(boost) < MAX_BOOST + 1 and len(re.findall(re.escape(spelled.split(" (")[0]), body, re.I)) < 2 and spelled not in boost:
            boost.append(spelled)
    if boost:
        lst = boost[0] if len(boost) == 1 else ", ".join(boost[:-1]) + " and " + boost[-1]
        v["summary"] = v["summary"].rstrip() + f" Hands-on with {engine.inline(lst)}."

    # 3. spelling mirrored everywhere
    v["headline"], v["summary"] = respell(v["headline"], smap), respell(v["summary"], smap)
    for g in R2["skills"].values():
        g["items"] = [respell(it, smap) for it in g["items"]]
    R2["bullets"] = {k: respell(t, smap) for k, t in R2["bullets"].items()}
    for j in R2["jobs"].values():
        j["stack"] = respell(j["stack"], smap)
    for pr in R2["projects"].values():
        pr["title"], pr["bullets"] = respell(pr["title"], smap), [respell(b, smap) for b in pr["bullets"]]
    return dict(v=v, R=R2, base=base, base_v=base_v, have=have, gaps=gaps, added=added, smap=smap,
                expanded=expanded, boost=boost)


def words(s):
    return collections.Counter(re.findall(r"[a-z0-9+#.]+", s.lower()))


def core_share(tailored_text, base_text):
    a, b = words(tailored_text), words(base_text)
    return sum((a & b).values()) / max(1, sum(a.values()))


def keyword_counts(text, t, terms):
    out = {}
    for k in t["have"]:
        if not T.is_generic(k, terms):
            out[k] = len(re.findall(count_rx(k), text, re.I))
    for _, _, _, spelled in t["added"]:
        out[spelled] = len(re.findall(re.escape(spelled.split(" (")[0]), text, re.I))
    return out


BENEFIT = re.compile(r"benefit|401k|insurance|pto|vacation|salary|compensation|equity|visa|equal opportunity|"
                     r"accommodation|privacy|interview|we offer|perks|parental", re.I)
YEARS = re.compile(r"\d+\+?\s*(-\s*\d+\s*)?years?", re.I)


def requirements(desc, terms, gaps_tbl, n=8):
    """Requirement-like lines: they name a tool/skill or a years-of-experience ask. Ranked by how many they name."""
    parts = re.split(r"[\n\r]+|(?<=[.;])\s+(?=[A-Z])|\s[•·▪]\s|\s-\s(?=[A-Z])", desc)
    seen, out = set(), []
    for i, l in enumerate(parts):
        l = re.sub(r"\*+|_{2,}", "", l).strip(" \t-*•·")
        if not (25 <= len(l) <= 300) or BENEFIT.search(l) or l.lower() in seen:
            continue
        seen.add(l.lower())
        kws = [k for k, t in terms.items() if not T.is_generic(k, terms) and re.search(t["rx"], l, re.I)]
        gaps = [k for k, rx in gaps_tbl.items() if re.search(rx, l, re.I)]
        yrs = bool(YEARS.search(l))
        score = len(kws) + len(gaps) + 2 * yrs
        if score:
            out.append((score, i, l, kws, gaps, yrs))
    top = sorted(out, key=lambda x: (-x[0], x[1]))[:n]
    return [(l, kws, gaps, yrs) for _, _, l, kws, gaps, yrs in sorted(top, key=lambda x: x[1])]


def evidence(reqs, t, terms, years=None):
    """Map each requirement to the bullet on THIS resume that names most of its keywords."""
    R2, v = t["R"], t["v"]
    pool = {b: engine.plain(R2["bullets"].get(b, b)) for bl in v["jobs"].values() for b in bl}
    for p in v["projects"]:
        if isinstance(p, str) and p in R2["projects"]:
            for i, b in enumerate(R2["projects"][p]["bullets"]):
                pool[f"{p}#{i + 1}"] = engine.plain(b)
    stacks = {k: engine.plain(j["stack"]) for k, j in R2["jobs"].items() if j["stack"]}
    out = []
    for r, kws, gaps, yrs in reqs:
        if not kws:
            note = ("gap: " + ", ".join(gaps)) if gaps else (f"{years or '?'} years total (summary)" if yrs else None)
            out.append((r, note, kws))
            continue
        hit = lambda txt: [k for k in kws if re.search(terms[k]["rx"], txt, re.I)]  # noqa: E731
        best = max(pool, key=lambda k: len(hit(pool[k]))) if pool else None
        got = hit(pool[best]) if best else []
        if got:
            miss = [k for k in kws if k not in got]
            out.append((r, f"{best} ({', '.join(got)})" + (f"; also in Skills: {', '.join(miss)}" if miss else ""), kws))
        else:
            st = [j for j, sx in stacks.items() if hit(sx)]
            out.append((r, f"Stack line of {', '.join(st)} only, no bullet" if st else None, kws))
    return out


def parse_check(pdf, counts, R, terms):
    from pypdf import PdfReader
    rd = PdfReader(pdf)
    txt = re.sub(r"\s+", " ", " ".join(pg.extract_text() or "" for pg in rd.pages))
    need = [R["name"]] + engine.contact_literals(R)[:1] + [R["titles"][k] for k in ("summary", "skills", "experience", "education")]
    missing = [n for n in need if engine.plain(n).lower() not in txt.lower()]
    lost = [k for k, c in counts.items() if c and k.lower().split(" (")[0] not in txt.lower()
            and not re.search(terms.get(k, {}).get("rx", re.escape(k)), txt, re.I)]
    return dict(pages=len(rd.pages), chars=len(txt), missing_sections=missing, keywords_lost_in_pdf=lost)


def pdf_checks(pdf, R, pages, exact=True):
    """ai-job-search's checks: page count, ASCII dates, literal contact text, layout. Returns a list of problems."""
    probs = []
    cmd = [sys.executable, os.path.join(RESUME_DIR, "verify_pdf.py"), pdf, "--ascii-dates"]
    if exact:
        cmd += ["--pages", str(pages)]
    for lit in engine.contact_literals(R):
        cmd += ["--contains", lit]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        probs.append("verify_pdf: " + ((r.stderr or r.stdout).strip().splitlines() or ["failed"])[-1][:300])
    # Two extractors must read the same words; a word only one of them sees was split or merged (kerning, ligatures)
    try:
        from pypdf import PdfReader
        wre = r"[A-Za-z][A-Za-z+#-]{2,}"
        a = set(re.findall(wre, " ".join(pg.extract_text() or "" for pg in PdfReader(pdf).pages)))
        b = set(re.findall(wre, subprocess.run(["pdftotext", pdf, "-"], capture_output=True, text=True).stdout))
        if a ^ b:
            probs.append("extractors disagree (split or merged words): " + ", ".join(sorted(a ^ b)[:12]))
    except (FileNotFoundError, ImportError):
        pass  # no Poppler or pypdf: the page-count check still ran
    r = subprocess.run([sys.executable, os.path.join(RESUME_DIR, "verify_layout.py"), "--footer-band", "0", pdf],
                       capture_output=True, text=True)
    if r.returncode == 1:
        probs += ["layout: " + l.strip(" -")[:200] for l in r.stdout.split("LAYOUT PROBLEMS:")[-1].strip().splitlines() if l.strip()]
    return probs


def run(jobs, out, ov=None, engine_name=None, R=None, inv=None, p=None):
    """Build every job; returns the index rows. Separate from main() so tests can call it."""
    p = engine.profile() if p is None else p
    R = R or engine.load_content(p=p)
    inv = inv if inv is not None else T.read_inventory()
    terms = T.candidate_terms(R, inv)
    gaps_tbl, familiar = T.gap_terms(terms, inv)
    ov = ov or {}
    engine_name = engine_name or engine.setting("engine", "latex", p)
    pages = int(engine.setting("pages", 2, p))
    exact = bool(engine.setting("exact_pages", True, p))
    years = config.get(p, "current_role.years_experience", None)
    stem = config.file_stem(p)
    can_pdf = (engine_name == "latex" and latex.have_tectonic()) or engine_name == "chrome"
    os.makedirs(out, exist_ok=True)
    index = []
    for job in jobs:
        t = tailor_one(R, job, terms, inv, ov)
        d = os.path.join(out, job["key"])
        os.makedirs(d, exist_ok=True)
        text = engine.resume_text(t["R"], t["v"])
        share = core_share(text, engine.resume_text(R, t["base_v"]))
        counts = keyword_counts(text, t, terms)
        res = build_one(t["R"], t["v"], os.path.join(d, f"{stem}_Resume"), {"html", "tex", "pdf", "docx"} if can_pdf
                        else {"html", "tex", "docx"}, engine_name, f"{R['name']} - {job['company']} - {job['title']}",
                        pages=pages)
        pc = {"pages": res.get("pages"), "checks": [], "spacing_level": res.get("spacing_level")}
        if res.get("pdf"):
            try:
                pc.update(parse_check(res["pdf"], counts, t["R"], terms))
            except ImportError:
                pc["checks"].append("pypdf missing: parse check skipped (run ./setup.sh)")
            pc["checks"] += pdf_checks(res["pdf"], t["R"], pages, exact)
        else:
            pc["checks"].append("no PDF built (install tectonic, or --engine chrome)")
        reqs = requirements(job["desc"], terms, gaps_tbl)
        ev = evidence(reqs, t, terms, years)
        low = [k for k, c in counts.items() if c < 2]
        noev = [r for r, b, _ in ev if not b]
        fam = [k for k, rx in familiar.items() if re.search(rx, job["desc"], re.I)]
        with open(os.path.join(d, "keywords.md"), "w", encoding="utf-8") as f:
            f.write(f"# {job['company']}: {job['title']}\n\n{job.get('url', '')}\n\n"
                    f"Tracker row {job.get('row', '?')} · score {job.get('score', '?')}"
                    + (f" · {job['h1b']}" if job.get("h1b") else "") + "\n\n"
                    f"Base version: {t['base']} · core share {share:.0%} (target 70%+)\n\n"
                    f"Headline: {engine.plain(t['v']['headline'])}\n\n"
                    "## Tuned for this job (the 30%)\n"
                    f"- Spelling mirrored from the posting: {', '.join(f'{k} -> {x}' for k, x in t['smap'].items()) or 'none'}\n"
                    f"- Acronyms spelled out: {', '.join(t['expanded']) or 'none'}\n"
                    f"- Summary closer added for must-haves: {', '.join(t['boost']) or 'none'}\n"
                    f"- Tools added from the skills inventory: {', '.join(f'{s} ({w})' for _, w, _, s in t['added']) or 'none'}\n"
                    "- Skill lines, terms and bullets reordered so matched keywords come first\n\n"
                    "## Keyword mentions in the resume (target 2-3)\n" +
                    "".join(f"- {k}: {c}{'  << only once' if c < 2 else ''}\n" for k, c in sorted(counts.items(), key=lambda x: x[1])) +
                    "\n## Requirements -> evidence bullet\n" +
                    "".join(f"- {r}\n  -> {b or 'NO EVIDENCE BULLET: answer in the cover note or skip'}\n" for r, b, _ in ev) +
                    "\n## Gaps (asked for, not used; never added)\n" + (", ".join(t["gaps"]) or "none found") +
                    ("\n\n## Familiar only (Skills line at most, never in a bullet; candidate decides)\n" + ", ".join(fam) if fam else "") +
                    f"\n\n## Parse check\n{json.dumps(pc)}\n")
        flags = []
        if share < CORE_TARGET:
            flags.append(f"core share {share:.0%}")
        if pc.get("missing_sections") or pc.get("keywords_lost_in_pdf"):
            flags.append("parse")
        if (pc.get("pages") or 0) > pages:
            flags.append(f"{pc['pages']} pages")
        if pc["checks"]:
            flags.append("checks")
        index.append(dict(row=job.get("row"), company=job["company"], title=job["title"], url=job.get("url"),
                          dir=d, base=t["base"], core_share=f"{share:.0%}", matched=len(t["have"]),
                          added=";".join(s for *_, s in t["added"]), once=";".join(low),
                          no_evidence=len(noev), gaps=";".join(t["gaps"]), pages=pc.get("pages"), flags=";".join(flags)))
        print(f"{job['key'][:48]:<48} {t['base']:<11} core {share:.0%} | +{len(t['added'])} tools | "
              f"once {len(low)} | no-evidence {len(noev)} | gaps {len(t['gaps'])} | {pc.get('pages')}p "
              f"{'| ' + ','.join(flags) if flags else ''}")
    if index:
        path = os.path.join(out, "index.csv")
        old = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                old = {r["dir"]: r for r in csv.DictReader(f)}
        for r in index:
            old[r["dir"]] = r
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(index[0].keys()))
            w.writeheader()
            w.writerows(old.values())
        print(f"wrote {len(index)} resumes; index: {path}")
    return index


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--overrides")
    ap.add_argument("--only", help="comma-separated keys")
    ap.add_argument("--engine", default=None, choices=["latex", "chrome"])
    a = ap.parse_args()
    p = config.load()
    if not config.module_on(p, "resume_tailoring"):
        sys.exit("modules.resume_tailoring is off in config/profile.json; turn it on to tailor resumes.")
    jobs = json.load(open(a.jobs, encoding="utf-8"))
    if a.only:
        keep = set(a.only.split(","))
        jobs = [j for j in jobs if j["key"] in keep]
    ov = json.load(open(a.overrides, encoding="utf-8")) if a.overrides and os.path.exists(a.overrides) else {}
    run(jobs, a.out, ov, a.engine, p=p)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Build one fully tailored resume from <dir>/custom.json (full mode, ai-job-search style) and check it.

custom.json:
  headline       str
  summary        str   (profile statement, 4-6 rendered lines)
  skills         [[label, items], ...]   5-8 lines, posting's terms in labels, tools only from the candidate's files
  jobs           {"<job id>": [bullet, ...], ...}   ids from resume_content.json, in its order; bullets rewritten for
                 the posting from master_cv.md facts; <b>..</b> allowed; an existing bullet id is also accepted
  stack          {"<job id>": "..."}   optional reordered stack line per job (same tools only)
  projects_title str
  projects       [[title, [bullet, ...]], ...] or project ids; titles exactly as in resume_content.json

Guard (fails the build): a tool the candidate has not used (catalog gaps + the inventory's "Never claim" list),
a "familiar only" tool inside a bullet, any number not in profile/master_cv.md or resume_content.json, jobs out of
order or missing (a job may be dropped only if it has "optional": true), an empty job, a changed project title.

Usage (repo root): .venv/bin/python .claude/skills/build-batch-resume/scripts/build_custom.py <dir> [<dir> ...]
Writes <dir>/<First_Last>_Resume.{tex,pdf,html,docx}, <dir>/ats.txt and <dir>/checks.txt; exit 1 if any check fails.
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tailor as T  # noqa: E402  (bootstraps the repo root onto sys.path)
from core import config  # noqa: E402
from resume import engine, latex  # noqa: E402


# Concepts that are claims of experience, never just the company's vocabulary
HARD_CONCEPTS = {"model training/fine-tuning", "CUDA/GPU", "embedded/firmware", "robotics", "security clearance", "compilers"}


def numbers(s):
    return set(re.findall(r"\d[\d,.]*\+?%?", engine.plain(s)))


def allowed_numbers(R, p):
    src = json.dumps(R["raw"], ensure_ascii=False)
    mp = config.path("profile", "master_cv.md")
    if os.path.exists(mp):
        with open(mp, encoding="utf-8") as f:
            src += f.read()
    yrs = str(config.get(p, "current_role.years_experience", "") or "")
    return numbers(src) | {"1", "2", "3", "4", "5"} | ({yrs} if yrs else set())


def guard(cj, R, p=None, inv=None):
    """Problems with a custom.json, as a list of strings (empty = OK)."""
    p = engine.profile() if p is None else p
    inv = inv if inv is not None else T.read_inventory()
    terms = T.candidate_terms(R, inv)
    gaps, familiar = T.gap_terms(terms, inv)
    probs = []
    jobs = cj.get("jobs", {})
    bullets = [R["bullets"].get(b, b) for bl in jobs.values() for b in bl]
    proj = [pr for pr in cj.get("projects", [])]
    proj_bullets = [b for pr in proj if not isinstance(pr, str) for b in pr[1]]
    skills_text = " ".join(f"{a} {b if isinstance(b, str) else ', '.join(b)}" for a, b in cj.get("skills", []))
    prose = " ".join([cj.get("headline", ""), cj.get("summary", "")] + bullets + list(cj.get("stack", {}).values()) + proj_bullets)
    text = engine.plain(prose + " " + skills_text)
    never = {T.catalog_term_for(t) or t for t in inv["never"]}
    for term, rx in gaps.items():
        if term in T.K.CONCEPT and term not in HARD_CONCEPTS and term not in never:
            continue  # domains and practices: the summary may use the company's words for its problem
        m = re.search(rx, text, re.I)
        if m:
            probs.append(f"not-used tool: '{m.group(0)}' ({term})")
    for tool, rx in familiar.items():
        m = re.search(rx, engine.plain(" ".join(bullets + proj_bullets)), re.I)
        if m:
            probs.append(f"familiar-only tool in a bullet: '{m.group(0)}' (Skills line at most)")
    allowed = allowed_numbers(R, p)
    bare = {x.rstrip("%+,.") for x in allowed}
    for n in sorted(numbers(prose + " " + skills_text)):
        if n not in allowed and n.rstrip("%+,.") not in bare:
            probs.append(f"number not in master_cv/resume_content: '{n}'")
    order = list(R["jobs"])
    keys = list(jobs)
    unknown = [k for k in keys if k not in R["jobs"]]
    if unknown:
        probs.append(f"unknown job ids {unknown} (use the ids in resume_content.json)")
    known = [k for k in keys if k in R["jobs"]]
    if known != [k for k in order if k in known]:
        probs.append(f"jobs must keep the resume order {order} (got {keys})")
    missing = [k for k in order if k not in jobs and not R["jobs"][k]["optional"]]
    if missing:
        probs.append(f"jobs missing (never drop a whole job unless it is marked optional): {missing}")
    for k in keys:
        if not jobs[k]:
            probs.append(f"job {k} has no bullets (every listed job needs at least one)")
    titles = {engine.plain(pr["title"]) for pr in R["projects"].values()}
    for pr in proj:
        if isinstance(pr, str):
            if pr not in R["projects"]:
                probs.append(f"unknown project id '{pr}'")
        elif engine.plain(pr[0]) not in titles:
            probs.append(f"project title changed: '{pr[0]}'")
    return probs


def to_version(cj):
    return {"headline": engine.inline(cj["headline"]), "summary": engine.inline(cj["summary"]),
            "skills": [tuple(x) for x in cj["skills"]], "jobs": cj["jobs"], "stack": cj.get("stack", {}),
            "projects_title": engine.inline(cj.get("projects_title", "")),
            "projects": [pr if isinstance(pr, str) else (pr[0], pr[1]) for pr in cj.get("projects", [])]}


def build(d, R=None, p=None):
    p = engine.profile() if p is None else p
    R = R or engine.load_content(p=p)
    with open(os.path.join(d, "custom.json"), encoding="utf-8") as f:
        cj = json.load(f)
    pages_target = int(engine.setting("pages", 2, p))
    probs = guard(cj, R, p)
    base = os.path.join(d, f"{config.file_stem(p)}_Resume")
    v = to_version(cj)
    pages, level = latex.build_fit(R, v, base, f"{R['name']} - Resume", "", pages_target)
    with open(base + ".html", "w", encoding="utf-8") as f:   # keep every format in step with custom.json
        f.write(engine.html_version(R, v))
    if engine.have_docx():
        engine.docx_version(R, v, base + ".docx")
    pdf = base + ".pdf"
    if pages != pages_target:
        probs.append(f"pages = {pages} at spacing level {level} (must be exactly {pages_target}: cut the least relevant "
                     "line, or restore one if short)")
    rd = config.path("resume")
    cmd = [sys.executable, os.path.join(rd, "verify_pdf.py"), pdf, "--pages", str(pages_target), "--ascii-dates"]
    for lit in engine.contact_literals(R):
        cmd += ["--contains", lit]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        probs.append("verify_pdf: " + ((r.stderr or r.stdout).strip().splitlines() or ["failed"])[-1][:300])
    r = subprocess.run([sys.executable, os.path.join(rd, "verify_layout.py"), "--footer-band", "0", pdf],
                       capture_output=True, text=True)
    if r.returncode == 1:
        probs.append("verify_layout: " + " | ".join((r.stdout + r.stderr).strip().splitlines()[-4:])[:400])
    try:
        txt = subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", pdf, "-"], capture_output=True, text=True).stdout
    except FileNotFoundError:
        from pypdf import PdfReader
        txt = "\n".join(pg.extract_text() or "" for pg in PdfReader(pdf).pages)
    with open(os.path.join(d, "ats.txt"), "w", encoding="utf-8") as f:
        f.write(txt)
    rep = f"{os.path.basename(d)}: pages {pages}, spacing {level}, " + ("OK" if not probs else f"{len(probs)} problem(s)")
    with open(os.path.join(d, "checks.txt"), "w", encoding="utf-8") as f:
        f.write(rep + "\n" + "\n".join("- " + x for x in probs) + "\n")
    print(rep)
    for x in probs:
        print("  -", x)
    return not probs


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    ok = all([build(d.rstrip("/")) for d in sys.argv[1:]])
    sys.exit(0 if ok else 1)

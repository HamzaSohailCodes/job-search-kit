#!/usr/bin/env python3
"""Health check: is this kit set up and safe to run?

  python3 scripts/doctor.py          readable report, exit 1 if anything is broken
  python3 scripts/doctor.py --json   same checks as JSON (for /setup and tests)
  python3 scripts/doctor.py --offline  skip the GitHub visibility check

Levels: ok, warn (works, but something is missing or worth a look), fail (the kit can't run correctly).
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys

_d = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(_d, "core", "config.py")) and _d != os.path.dirname(_d):
    _d = os.path.dirname(_d)
sys.path.insert(0, _d)
from core import config  # noqa: E402

ROOT = config.ROOT
SKILLS = ["setup", "search-jobs", "apply-batch", "build-batch-resume", "cv-job-match",
          "review-emails", "follow-ups", "interview-prep", "search-contract-jobs"]
PLACEHOLDER = re.compile(r"\{[A-Z][A-Z0-9_ ]{2,}(?: or [^}]*)?\}")


class Report:
    def __init__(self):
        self.items = []

    def add(self, level, area, msg):
        self.items.append({"level": level, "area": area, "msg": msg})

    ok = lambda self, a, m: self.add("ok", a, m)  # noqa: E731
    warn = lambda self, a, m: self.add("warn", a, m)  # noqa: E731
    fail = lambda self, a, m: self.add("fail", a, m)  # noqa: E731

    @property
    def failed(self):
        return any(i["level"] == "fail" for i in self.items)


def rel(*parts):
    return os.path.join(ROOT, *parts)


def check_python(r):
    v = sys.version_info
    (r.ok if v >= (3, 9) else r.fail)("tools", f"python {v.major}.{v.minor}")


def check_profile(r):
    p_path = config.profile_path()
    if not os.path.exists(p_path):
        r.fail("profile", "config/profile.json missing: run /setup in Claude Code")
        return {}
    try:
        p = config.load()
    except ValueError as e:
        r.fail("profile", f"config/profile.json is not valid JSON: {e}")
        return {}
    errors, warns = config.validate(p)
    for e in errors:
        r.fail("profile", e)
    for w in warns:
        r.warn("profile", w)
    if not errors:
        r.ok("profile", f"config/profile.json valid for {config.full_name(p)}")
    return p


def check_files(r, p):
    needed = [("profile/answer_bank.md", "fail"), ("profile/master_cv.md", "warn"),
              ("profile/skills_inventory.md", "warn"), ("profile/stories.md", "warn"), ("soul.md", "warn"),
              ("memory/MEMORY.md", "warn")]
    for f, level in needed:
        fp = rel(f)
        if not os.path.exists(fp):
            r.add(level, "files", f"{f} missing: run ./setup.sh, then /setup")
            continue
        with open(fp, encoding="utf-8", errors="replace") as fh:
            left = PLACEHOLDER.findall(fh.read())
        if left:
            r.warn("files", f"{f} still has {len(left)} placeholder(s), e.g. {left[0]}: /setup fills these")
        else:
            r.ok("files", f)
    if p and not os.path.exists(rel("profile", "ashby_fill.js")):
        r.warn("files", "profile/ashby_fill.js not generated: python3 .claude/skills/apply-batch/scripts/make_fill_js.py")


def check_skills(r, p):
    missing = [s for s in SKILLS if not os.path.exists(rel(".claude", "skills", s, "SKILL.md"))]
    if missing:
        r.fail("skills", "missing .claude/skills/<name>/SKILL.md for: " + ", ".join(missing))
    else:
        r.ok("skills", f"{len(SKILLS)} skills in .claude/skills (they load when Claude Code opens this folder)")
    if not os.path.exists(rel("CLAUDE.md")):
        r.fail("skills", "CLAUDE.md missing: Claude won't know the house rules")


def check_modules(r, p):
    if not p:
        return
    if config.module_on(p, "resume_tailoring"):
        for t in ("tectonic", "pdftotext"):
            (r.ok if shutil.which(t) else r.warn)("resume", f"{t} {'found' if shutil.which(t) else 'not found (brew install tectonic poppler)'}")
        py = rel(".venv", "bin", "python")
        if not os.path.exists(py):
            r.warn("resume", ".venv missing: run ./setup.sh")
        else:
            res = subprocess.run([py, "-c", "import pypdf, docx"], capture_output=True)
            (r.ok if res.returncode == 0 else r.warn)("resume", ".venv has pypdf and python-docx" if res.returncode == 0
                                                       else ".venv lacks pypdf/python-docx: re-run ./setup.sh")
        if not os.path.exists(rel("profile", "resume_content.json")):
            r.warn("resume", "profile/resume_content.json missing: /setup builds it from your resume")
    if config.module_on(p, "h1b"):
        if not os.path.exists(rel("profile", "no_sponsor_companies.txt")):
            r.warn("h1b", "profile/no_sponsor_companies.txt missing: run ./setup.sh")
        if not os.path.exists(rel("modules", "h1b", "h1b_lookup.py")):
            r.fail("h1b", "modules.h1b is on but modules/h1b/h1b_lookup.py is missing")
        else:
            r.ok("h1b", "H-1B module on")
    if config.module_on(p, "c2c"):
        if not glob.glob(rel("modules", "c2c", "scraper", "*.py")):
            r.fail("c2c", "a contract work type is selected but modules/c2c/scraper is missing")
        else:
            labels = ", ".join(config.employment_label(t) for t in config.employment_types(p))
            r.ok("c2c", f"contract search on (work types: {labels})")


def check_privacy(r, offline):
    gi = rel(".gitignore")
    text = ""
    if os.path.exists(gi):
        with open(gi) as fh:
            text = fh.read()
    for pat in (".env", "*token*", ".venv/"):
        if pat not in text:
            r.warn("privacy", f".gitignore does not list {pat}")
    if offline or not shutil.which("gh") or not os.path.isdir(rel(".git")):
        return
    try:
        res = subprocess.run(["gh", "repo", "view", "--json", "visibility", "-q", ".visibility"],
                             cwd=ROOT, capture_output=True, text=True, timeout=15)
    except (subprocess.TimeoutExpired, OSError):
        r.warn("privacy", "could not check GitHub visibility (gh timed out)")
        return
    vis = res.stdout.strip().upper()
    if res.returncode != 0 or not vis:
        return  # no GitHub remote yet
    if vis == "PUBLIC" and os.path.exists(config.profile_path()):
        r.fail("privacy", "this repo is PUBLIC on GitHub and holds your profile: make it private (gh repo edit --visibility private)")
    else:
        r.ok("privacy", f"GitHub repo is {vis.lower()}")


def check_tracker(r, p):
    if p and config.sheet_url(p):
        r.ok("tracker", "tracker sheet set")
    if not os.path.exists(rel("tracker", "tracker.csv")):
        r.warn("tracker", "tracker/tracker.csv not exported yet (fine before your first search)")


def run(offline=False):
    r = Report()
    check_python(r)
    p = check_profile(r)
    check_files(r, p)
    check_skills(r, p)
    check_modules(r, p)
    check_tracker(r, p)
    check_privacy(r, offline)
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args()
    r = run(a.offline)
    if a.json:
        print(json.dumps({"failed": r.failed, "items": r.items}, indent=2))
    else:
        mark = {"ok": "\033[32m✓\033[0m", "warn": "\033[33m!\033[0m", "fail": "\033[31m✗\033[0m"}
        for i in r.items:
            print(f"  {mark[i['level']]} [{i['area']}] {i['msg']}")
        n = {k: sum(1 for i in r.items if i["level"] == k) for k in mark}
        print(f"\n  {n['ok']} ok, {n['warn']} warning(s), {n['fail']} problem(s)")
    sys.exit(1 if r.failed else 0)


if __name__ == "__main__":
    main()

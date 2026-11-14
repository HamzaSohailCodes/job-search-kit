"""Resume engine and tailoring: content loading, HTML/LaTeX rendering, keyword matching on a fake posting,
pick_jobs rules, the full-mode guard, and (when Tectonic / pypdf / Poppler / python-docx are present) real builds
with the PDF checks. Uses the fake Jane Doe fixtures only."""
import contextlib
import copy
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures")
os.environ["JOB_KIT_PROFILE"] = os.path.join(FIX, "profile.json")
os.environ["JOB_KIT_RESUME_CONTENT"] = os.path.join(FIX, "resume_content.json")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, ".claude", "skills", "build-batch-resume", "scripts"))

from core import config  # noqa: E402
from resume import engine, latex  # noqa: E402
from resume.build import build_one  # noqa: E402
import tailor as T  # noqa: E402
import tailor_batch as TB  # noqa: E402
import pick_jobs as PJ  # noqa: E402
import build_custom as BC  # noqa: E402

try:
    import pypdf  # noqa: F401
    HAVE_PYPDF = True
except ImportError:
    HAVE_PYPDF = False
HAVE_TECTONIC = latex.have_tectonic()
HAVE_POPPLER = bool(shutil.which("pdftotext"))

INVENTORY = """# Skills inventory

## Used, not on the base resume (allowed: Skills line + one honest bullet mention)

| Tool | Where |
|---|---|
| Datadog | acme |
| Amazon S3 | globex |
| {TOOL} | {job_id or skills-only} |

## Familiar only (Skills line at most, never in a bullet)

| Tool | Note |
|---|---|
| Vue | side project |

## Never claim
- Kubernetes
- Go
"""

POSTING = {
    "key": "examplecorp-senior-backend-engineer", "company": "ExampleCorp", "row": 7, "score": 86,
    "title": "Sr. Backend Engineer (Payments Team)", "url": "https://jobs.example.com/1",
    "desc": ("ExampleCorp builds scheduling software for clinics. Our customers include Datadog.\n"
             "What you'll bring:\n"
             "- 5+ years of backend experience with Node.js and TypeScript\n"
             "- Strong experience with Postgres and Kafka in production; Postgres tuning a plus\n"
             "- Experience with Amazon S3 and event-driven systems\n"
             "- Familiarity with Kubernetes and Go\n"
             "- Experience with continuous integration and delivery and Docker\n"
             "- Some Vue experience helps\n"
             "We offer great benefits and a 401k.\n") * 3,
}


def inv():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "skills_inventory.md")
    with open(p, "w") as f:
        f.write(INVENTORY)
    return T.read_inventory(p)


class Content(unittest.TestCase):
    def setUp(self):
        self.p = config.load()
        self.R = engine.load_content(p=self.p)

    def test_example_and_fixture_match(self):
        with open(os.path.join(ROOT, "templates", "profile", "resume_content.example.json")) as f, \
                open(os.path.join(FIX, "resume_content.json")) as g:
            self.assertEqual(json.load(f), json.load(g))

    def test_load(self):
        R = self.R
        self.assertEqual(R["name"], "Jane Doe")
        self.assertEqual(list(R["jobs"]), ["acme", "globex", "initech"])
        self.assertIn("acme_dash", R["bullets"])
        self.assertEqual(engine.contact_literals(R), ["jane.doe@example.com", "+1 555 0100"])
        self.assertIn("&amp;", R["skills"]["back"]["label"])  # bare & normalised
        self.assertEqual(R["default_version"], "FullStack")

    def test_header_from_profile_when_omitted(self):
        raw = copy.deepcopy(self.R["raw"])
        raw.pop("header")
        R = engine.normalise(raw, self.p)
        self.assertEqual(R["name"], "Jane Doe")
        self.assertIn("jane.doe@example.com", " ".join(R["contact"]))
        self.assertIn("Austin, TX", R["contact"][0])

    def test_html(self):
        for name in self.R["versions"]:
            h = engine.html_version(self.R, engine.version(self.R, name))
            self.assertIn("<h1>Jane Doe</h1>", h)
            self.assertIn("Cut dashboard load time by 60%", h)
            self.assertIn("Example State University", h)
            self.assertIn("Community", h)
        v = engine.version(self.R, "Backend")
        txt = engine.resume_text(self.R, v)
        self.assertLess(txt.index("Backend &"), txt.index("Frontend:"))  # version's skill order

    def test_tex(self):
        src = latex.tex_version(self.R, engine.version(self.R))
        self.assertNotRegex(src, r"(19|20)\d{2}\s*[–—]\s*((19|20)\d{2}|Present)")
        self.assertIn("Mar 2021 - Present", src)
        self.assertIn("Kerning=Off", src)
        self.assertIn(r"\hyphenpenalty=10000", src)
        self.assertIn(r"\needspace", src)
        self.assertIn(r"\textbf{\color{navy}Cut dashboard load time by 60\%}", src)
        self.assertIn("pdfauthor={Jane Doe}", src)
        self.assertIn(r"\href{https://acme.example.com}{Acme Analytics}", src)

    def test_custom_version_shapes(self):
        v = {"headline": "X", "summary": "Y", "skills": [("Tools", ["A", "B"])], "jobs": {"acme": ["acme_dash", "free text"]},
             "projects": [("P", ["b"])]}
        h = engine.html_version(self.R, v)
        self.assertIn("<b>Tools:</b> A, B", h)
        self.assertIn("<li>free text</li>", h)


class Escaping(unittest.TestCase):
    def test_special_characters(self):
        self.assertEqual(latex.tex("~25% of $4.5M &amp; R_D #1"), r"\textasciitilde{}25\% of \$4.5M \& R\_D \#1")

    def test_inline_html(self):
        got = latex.tex('<b>Grew X by ~40%</b> and <i>t</i> at <a class="co" href="https://acme.example.com">Acme</a>')
        self.assertEqual(got, r"\textbf{Grew X by \textasciitilde{}40\%} and \textit{t} at \href{https://acme.example.com}{Acme}")

    def test_ascii_dates_only_for_ranges(self):
        self.assertEqual(latex.ascii_dates("Remote | Sep 2025 – Present"), "Remote | Sep 2025 - Present")
        self.assertEqual(latex.ascii_dates("2016 – 2020"), "2016 - 2020")
        self.assertEqual(latex.ascii_dates("Certified Data Engineer – Associate"), "Certified Data Engineer – Associate")


class Tailoring(unittest.TestCase):
    def setUp(self):
        self.R = engine.load_content()
        self.inv = inv()
        self.terms = T.candidate_terms(self.R, self.inv)

    def test_inventory_parse(self):
        self.assertEqual(self.inv["used"], [("Datadog", "acme"), ("Amazon S3", "globex")])
        self.assertEqual(self.inv["familiar"], [("Vue", "side project")])
        self.assertEqual(self.inv["never"], ["Kubernetes", "Go"])

    def test_candidate_terms(self):
        for k in ("TypeScript", "PostgreSQL", "Kafka", "Terraform", "RAG", "Datadog", "Amazon S3", "code review"):
            self.assertIn(k, self.terms)
        for k in ("Go", "Kubernetes", "Vue", "Rust", "Java"):
            self.assertNotIn(k, self.terms)

    def test_match_and_gaps(self):
        v, R2, base, have, gaps = T.tailor(self.R, POSTING, self.terms, self.inv)
        self.assertEqual(base, "Backend")
        for k in ("Node.js", "TypeScript", "PostgreSQL", "Kafka", "Docker", "event-driven"):
            self.assertIn(k, have)
        self.assertEqual(sorted(gaps), ["Go", "Kubernetes"])          # Vue is familiar: not a gap
        self.assertNotIn("JavaScript", have)                         # "Node.js" is not a JavaScript ask
        self.assertEqual(v["jobs"]["acme"][-1], "acme_lead")          # bullets naming no matched keyword go last

    def test_tailor_one_70_30(self):
        t = TB.tailor_one(self.R, POSTING, self.terms, self.inv, {})
        self.assertEqual(t["smap"], {"PostgreSQL": "Postgres"})
        self.assertTrue(engine.plain(t["v"]["headline"]).startswith("Senior Backend Engineer · "))
        self.assertNotIn("Payments", t["v"]["headline"])
        self.assertEqual([a[3] for a in t["added"]], ["Amazon S3"])   # Datadog only in a customer list
        self.assertIn("globex", [a[1] for a in t["added"]])
        self.assertIn("Amazon S3", t["R"]["jobs"]["globex"]["stack"])
        self.assertIn("CI/CD", t["expanded"])
        text = engine.resume_text(t["R"], t["v"])
        self.assertNotIn("PostgreSQL", text)
        self.assertIn("Postgres", text)
        self.assertNotRegex(text, r"\b(Kubernetes|Vue)\b")
        self.assertNotRegex(text, r"(?-i:\bGo\b)")
        share = TB.core_share(text, engine.resume_text(self.R, t["base_v"]))
        self.assertGreaterEqual(share, TB.CORE_TARGET)
        # every bullet's wording is unchanged apart from mirrored spelling
        for b, txt in self.R["bullets"].items():
            self.assertEqual(t["R"]["bullets"][b], TB.respell(txt, t["smap"]))

    def test_overrides(self):
        ov = {POSTING["key"]: {"summary_lead": "Backend engineer with 7 years of experience, including clinic-scale data pipelines.",
                               "reorder": [["acme_tenant", "acme_dash"]], "swap": [["acme_ai", "acme_lead"]]}}
        R = copy.deepcopy(self.R)
        R["versions"]["Backend"]["jobs"]["acme"].remove("acme_ai")   # swap brings in a bullet the version leaves out
        t = TB.tailor_one(R, POSTING, self.terms, self.inv, ov)
        self.assertTrue(t["v"]["summary"].startswith("Backend engineer with 7 years"))
        self.assertLess(t["v"]["jobs"]["acme"].index("acme_tenant"), t["v"]["jobs"]["acme"].index("acme_dash"))
        self.assertIn("acme_ai", t["v"]["jobs"]["acme"])
        self.assertNotIn("acme_lead", t["v"]["jobs"]["acme"])

    def test_requirements_and_evidence(self):
        gaps_tbl, _ = T.gap_terms(self.terms, self.inv)
        reqs = TB.requirements(POSTING["desc"], self.terms, gaps_tbl)
        self.assertTrue(any("Kafka" in r[0] for r in reqs))
        t = TB.tailor_one(self.R, POSTING, self.terms, self.inv, {})
        ev = dict((r, b) for r, b, _ in TB.evidence(reqs, t, self.terms, 7))
        kafka = next(r for r in ev if "Kafka" in r)
        self.assertIn("acme_dash", ev[kafka])
        gap = next(r for r in ev if "Kubernetes" in r)
        self.assertTrue(ev[gap].startswith("gap:"))

    def test_clean_title(self):
        self.assertEqual(TB.clean_title("Sr. Software Engineer, Growth"), "Senior Software Engineer")
        self.assertEqual(TB.clean_title("Software Engineer (Full Stack)"), "Software Engineer, Full Stack")
        self.assertEqual(TB.clean_title("Senior Engineer - Platform Team | Acme"), "Senior Engineer")


class PickJobs(unittest.TestCase):
    def row(self, company, status="Shortlisted", score="85", posted="2026-11-01", desc=None, title="Senior Engineer"):
        return {"Company": company, "Job Title": title, "Apply Status": status, "Match Score": score,
                "Job Posted At": posted, "Job Description": desc if desc is not None else "x" * 1600,
                "Job Link": "https://jobs.example.com", "Location": "Remote", "Pay Scale": "", "H-1B Evidence": ""}

    def test_rules(self):
        p = config.load()
        rows = [self.row("Alpha"), self.row("Alpha", score="90", title="Staff Engineer"),
                self.row("Beta", status="Applied"), self.row("Beta"), self.row("Gamma", score="60"),
                self.row("Delta", posted="2026-09-01"), self.row("Epsilon", posted="~2026-11-02"),
                self.row("Zeta", desc="short"), self.row("Eta", desc="Requires an active TS/SCI clearance. " + "x" * 1600),
                self.row("Theta", score="95")]
        jobs, drops = PJ.pick(rows, p, n=10, days=21, min_score=70, today="2026-11-08", tailored={"theta-senior-engineer"})
        self.assertEqual([j["company"] for j in jobs], ["Alpha"])
        self.assertEqual(jobs[0]["title"], "Staff Engineer")          # higher score wins within a company
        for why in ("company already applied/skipped", "score", "old", "approx date", "thin description",
                    "domain skip: clearance", "already tailored", "second role at company"):
            self.assertIn(why, drops)
        self.assertEqual(jobs[0]["key"], "alpha-staff-engineer")


class CustomGuard(unittest.TestCase):
    def test_guard(self):
        R = engine.load_content()
        good = {"headline": "Senior Backend Engineer · Node.js", "summary": "Backend engineer with 7 years of experience.",
                "skills": [["Backend", "Node.js, Postgres, Datadog, Vue"]],
                "jobs": {"acme": ["acme_dash", "Cut dashboard load time by 60% with Kafka."], "globex": ["globex_track"],
                         "initech": ["initech_tools"]},
                "projects": [["MetricsBot | Open-source Slack bot · 2023", ["Built a Slack bot."]]]}
        self.assertEqual(BC.guard(good, R, inv=inv()), [])
        bad = copy.deepcopy(good)
        bad["summary"] += " Runs Kubernetes and Go. Grew revenue 75%."
        bad["jobs"] = {"globex": ["Built a Vue screen."], "acme": ["acme_dash"]}
        bad["projects"] = [["Renamed", ["x"]]]
        probs = " | ".join(BC.guard(bad, R, inv=inv()))
        for s in ("Kubernetes", "'Go'", "familiar-only tool in a bullet: 'Vue'", "'75%'", "resume order", "jobs missing",
                  "project title changed"):
            self.assertIn(s, probs)


@unittest.skipUnless(HAVE_TECTONIC and HAVE_PYPDF, "needs tectonic and pypdf (./setup.sh, brew install tectonic)")
class PdfBuild(unittest.TestCase):
    def test_build_fit_and_checks(self):
        import resume.verify_pdf as verify_pdf
        R = engine.load_content()
        with tempfile.TemporaryDirectory() as d:
            base = os.path.join(d, "r")
            n, level = latex.build_fit(R, engine.version(R, "Backend"), base, pages=2)
            self.assertLessEqual(n, 2)
            text, pages, _ = verify_pdf.extract_text_layer(base + ".pdf")
            self.assertEqual(pages, n)
            self.assertIn("jane.doe@example.com", text)
            self.assertIn("+1 555 0100", text)
            self.assertEqual(verify_pdf.find_non_ascii_date_ranges(text), [])
            r = subprocess.run([sys.executable, os.path.join(ROOT, "resume", "verify_pdf.py"), base + ".pdf", "--pages", str(n),
                                "--ascii-dates", "--contains", "jane.doe@example.com"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            if HAVE_POPPLER:
                r = subprocess.run([sys.executable, os.path.join(ROOT, "resume", "verify_layout.py"), "--footer-band", "0",
                                    base + ".pdf"], capture_output=True, text=True)
                self.assertNotIn("orphan", r.stdout.lower())

    def test_batch_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            with contextlib.redirect_stdout(io.StringIO()):
                idx = TB.run([POSTING], d, {}, "latex", inv=inv())
            self.assertEqual(len(idx), 1)
            jd = os.path.join(d, POSTING["key"])
            for ext in ("pdf", "tex", "html"):
                self.assertTrue(os.path.exists(os.path.join(jd, f"Jane_Doe_Resume.{ext}")))
            with open(os.path.join(jd, "keywords.md")) as f:
                kw = f.read()
            self.assertIn("Base version: Backend", kw)
            self.assertIn("Gaps (asked for, not used; never added)\nGo, Kubernetes", kw)
            self.assertIn("Familiar only", kw)
            pc = json.loads(kw.split("## Parse check\n")[1])
            self.assertEqual(pc["missing_sections"], [])
            self.assertEqual(pc["keywords_lost_in_pdf"], [])
            self.assertFalse([c for c in pc["checks"] if "verify_pdf" in c or "extractors disagree" in c], pc["checks"])
            self.assertTrue(os.path.exists(os.path.join(d, "index.csv")))

    def test_cover_letter(self):
        from resume import cover
        R = engine.load_content()
        letter = {"company": "ExampleCorp", "role": "Senior Backend Engineer", "date": "November 8, 2026",
                  "paragraphs": ["I would like to apply.", "At Acme Analytics I cut dashboard load time by 60%."]}
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "c.tex")
            with open(p, "w") as f:
                f.write(cover.cover_tex(letter, R))
            latex.tex_to_pdf(p)
            self.assertEqual(latex.pdf_pages(p[:-4] + ".pdf"), 1)


@unittest.skipUnless(engine.have_docx(), "needs python-docx (./setup.sh)")
class Docx(unittest.TestCase):
    def test_docx(self):
        import docx
        R = engine.load_content()
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "r.docx")
            engine.docx_version(R, engine.version(R), p)
            text = "\n".join(par.text for par in docx.Document(p).paragraphs)
            self.assertIn("Jane Doe", text)
            self.assertIn("Cut dashboard load time by 60%", text)
            self.assertIn("Backend & APIs: ", text)


class BuildCli(unittest.TestCase):
    def test_build_one_html(self):
        R = engine.load_content()
        with tempfile.TemporaryDirectory() as d:
            res = build_one(R, engine.version(R), os.path.join(d, "x"), {"html"}, "latex")
            h = open(res["html"], encoding="utf-8").read()
            self.assertIn("<title>Jane Doe — Resume</title>", h)

    @unittest.skipIf(HAVE_TECTONIC, "only meaningful without tectonic")
    def test_tex_without_tectonic(self):
        R = engine.load_content()
        with tempfile.TemporaryDirectory() as d:
            res = build_one(R, engine.version(R), os.path.join(d, "x"), {"tex"}, "latex")
            self.assertTrue(os.path.exists(res["tex"]))


if __name__ == "__main__":
    unittest.main()

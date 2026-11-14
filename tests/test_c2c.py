"""Tests for the optional C2C module: config mapping, filters on fake postings, shortlist dedupe,
email drafts. No network: only local functions and `run.py --check-config` are exercised."""
import copy
import csv
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "profile.json")
os.environ["JOB_KIT_PROFILE"] = FIXTURE
SCRAPER = os.path.join(ROOT, "modules", "c2c", "scraper")
OUTREACH = os.path.join(ROOT, "modules", "c2c", "outreach")
sys.path.insert(0, ROOT)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


common = _load("c2c_common", os.path.join(SCRAPER, "common.py"))
filters = _load("c2c_filters", os.path.join(SCRAPER, "filters.py"))
settings = _load("c2c_settings", os.path.join(SCRAPER, "settings.py"))
emails = _load("c2c_build_emails", os.path.join(OUTREACH, "build_emails.py"))
sys.path.insert(0, OUTREACH)
outreach = _load("c2c_build_outreach", os.path.join(OUTREACH, "build_outreach.py"))
shortlist = _load("c2c_shortlist", os.path.join(ROOT, ".claude", "skills", "search-contract-jobs", "scripts", "shortlist.py"))
Job = common.Job

VISA = ("h1b", "h-1b", "visa", "gc ead", "opt ", "cpt")


def fixture():
    """The fake Jane Doe profile, merged with config/profile.example.json defaults like config.load() does."""
    return copy.deepcopy(settings.config.load())


def profile(**over):
    """Fixture profile with dotted-key overrides, e.g. profile(**{"pay.hourly_floor": 0})."""
    p = fixture()
    for k, v in over.items():
        cur = p
        parts = k.split(".")
        for part in parts[:-1]:
            cur = cur.setdefault(part, {})
        cur[parts[-1]] = v
    return p


def job(**kw):
    base = dict(source="dice", title="Senior Full Stack Engineer", company="Acme Staffing",
                url="https://www.dice.com/job-detail/1", posted=date.today().isoformat(), location="Remote",
                remote=True, employment="DICE_C2C",
                description="Remote. 5+ years of software development experience with TypeScript, React, "
                            "Node.js, Python and PostgreSQL on AWS. LLM and RAG work is a plus.")
    base.update(kw)
    return Job(**base)


class ConfigMappingTest(unittest.TestCase):
    def test_fixture_maps_to_settings(self):
        s = settings.from_profile(fixture())
        self.assertTrue(s["enabled"])  # fixture picks full_time + contract_c2c
        self.assertEqual(s["contract_types"], ["contract_c2c"])
        self.assertEqual(s["hourly_floor"], 85)
        self.assertEqual(s["years"], 7)
        self.assertEqual(s["level"], "senior")
        self.assertFalse(s["needs_sponsorship"])
        self.assertTrue(s["us_citizen"])
        self.assertEqual((s["days"], s["max_years_asked"], s["remote_only"]), (30, 12, True))
        self.assertEqual(s["min_score"], 55)
        self.assertTrue(s["skip_clearance"])
        self.assertIn("typescript", s["skills"]["core"])
        self.assertEqual(s["skills"]["ai"], ["llm", "rag"])
        self.assertEqual(s["title_include"], settings.DEFAULT_TITLE_INCLUDE)
        self.assertEqual(s["title_exclude"], settings.DEFAULT_TITLE_EXCLUDE)
        self.assertTrue(s["firm_boards"].endswith(os.path.join("modules", "c2c", "scraper", "firm_boards.json")))

    def test_module_follows_employment_types(self):
        self.assertFalse(settings.from_profile(profile(**{"targets.employment_types": ["full_time"]}))["enabled"])
        s = settings.from_profile(profile(**{"targets.employment_types": ["contract_w2", "contract_1099"]}))
        self.assertTrue(s["enabled"])
        self.assertEqual(s["contract_types"], ["contract_w2", "contract_1099"])

    def test_1099_never_when_sponsorship_needed(self):
        s = settings.from_profile(profile(**{"targets.employment_types": ["contract_c2c", "contract_1099"],
                                             "work_authorization.needs_sponsorship": True}))
        self.assertEqual(s["contract_types"], ["contract_c2c"])
        self.assertFalse(any(q.startswith("1099") for q in s["queries"]["dice_keyword"]))

    def test_queries_generated_without_visa_terms(self):
        s = settings.from_profile(fixture())
        self.assertEqual(sorted(s["queries_generated"]), ["dice", "dice_keyword", "linkedin"])
        for k in ("dice", "dice_keyword", "linkedin"):
            self.assertTrue(s["queries"][k], k)
            for q in s["queries"][k]:
                self.assertFalse(settings.VISA_TERMS.search(q), f"visa term in {k}: {q}")
        self.assertIn("senior software engineer", s["queries"]["dice"])
        self.assertIn("c2c typescript", s["queries"]["dice_keyword"])
        self.assertIn("corp to corp developer", s["queries"]["linkedin"])
        self.assertFalse(any(q.startswith("w2") for q in s["queries"]["dice_keyword"]))

    def test_queries_follow_contract_types(self):
        s = settings.from_profile(profile(**{"targets.employment_types": ["contract_w2"]}))
        kw = s["queries"]["dice_keyword"]
        self.assertTrue(kw and all(q.startswith("w2 contract") for q in kw), kw)

    def test_visa_terms_only_when_sponsorship_needed(self):
        s = settings.from_profile(profile(**{"work_authorization.needs_sponsorship": True,
                                             "work_authorization.citizenship": "India"}))
        self.assertTrue(s["needs_sponsorship"])
        self.assertFalse(s["us_citizen"])
        self.assertTrue(any(q.startswith("h1b ") for q in s["queries"]["dice_keyword"]))
        self.assertIn("h1b c2c developer", s["queries"]["linkedin"])

    def test_overrides_from_c2c_section(self):
        p = profile(**{"c2c.queries": {"dice": ["golang contract"], "dice_keyword": [], "linkedin": []},
                       "c2c.title_include": ["Go Developer"], "c2c.title_exclude": ["intern"],
                       "c2c.days": 7, "c2c.max_years_asked": 9, "c2c.remote_only": False,
                       "c2c.min_score": 60, "c2c.skip_clearance": False,
                       "current_role.years_experience": 4, "current_role.level": "Mid"})
        s = settings.from_profile(p)
        self.assertEqual(s["queries"]["dice"], ["golang contract"])
        self.assertEqual(s["queries_generated"], ["dice_keyword", "linkedin"])
        self.assertEqual(s["title_include"], ["go developer"])
        self.assertEqual(s["title_exclude"], ["intern"])
        self.assertEqual((s["days"], s["max_years_asked"], s["remote_only"]), (7, 9, False))
        self.assertEqual((s["min_score"], s["skip_clearance"], s["years"], s["level"]), (60, False, 4, "mid"))


class RunScriptTest(unittest.TestCase):
    def _run(self, p):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "profile.json")
            with open(path, "w") as f:
                json.dump(p, f)
            env = dict(os.environ, JOB_KIT_PROFILE=path)
            return subprocess.run([sys.executable, os.path.join(SCRAPER, "run.py"), "--check-config"],
                                  capture_output=True, text=True, env=env, cwd=ROOT, timeout=60)

    def test_module_off_stops_with_instructions(self):
        r = self._run(profile(**{"targets.employment_types": ["full_time"]}))
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertIn("/setup → update my profile (targets.employment_types", r.stderr)

    def test_check_config_when_on(self):
        r = self._run(fixture())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("queries.dice (generated)", r.stderr)
        self.assertIn("contract_types: contract_c2c", r.stderr)
        self.assertIn("needs_sponsorship: False", r.stderr)


class FilterTest(unittest.TestCase):
    def setUp(self):
        self.prof = settings.from_profile(fixture())
        self.sponsor = settings.from_profile(profile(**{"work_authorization.needs_sponsorship": True,
                                                        "work_authorization.citizenship": "India"}))

    def check(self, j, prof=None):
        return filters.check(j, prof or self.prof)

    def typed(self, *types, **over):
        over["targets.employment_types"] = ["full_time"] + list(types)
        return settings.from_profile(profile(**over))

    def test_good_role_kept_and_scored(self):
        ok, why = self.check(job())
        self.assertTrue(ok, why)
        s, info = filters.score(job(), self.prof)
        self.assertGreaterEqual(s, 70)
        self.assertEqual(info["c2c"], "yes")
        self.assertEqual(info["employment_type"], "contract_c2c")
        self.assertEqual(info["terms"], "C2C confirmed, remote")
        self.assertEqual(info["years_asked"], 5)
        self.assertIn("react", info["skills_hit"])

    def test_drops(self):
        old = (date.today() - timedelta(days=45)).isoformat()
        cases = {
            "title outside stack/level": job(title="Senior Java Developer"),
            "title not a target role": job(title="Business Analyst"),
            "older than window": job(posted=old),
            "rules out C2C": job(employment="DICE_NO_C2C"),
            "not a contract role (Dice: full/part time)": job(employment="DICE_NOT_CONTRACT"),
            "only W2 (type not selected)": job(employment="CONTRACT", description="Remote contract. W2 only, no C2C."),
            "hybrid/onsite": job(title="Full Stack Engineer - Hybrid"),
            "not remote": job(remote=False),
            "needs clearance": job(description="Remote. Active Secret clearance required. React, Node."),
            "asks 15+ years": job(description="Remote. 15+ years of software development experience."),
            "rate below pay.hourly_floor": job(pay="$60-70"),
        }
        for want, j in cases.items():
            ok, why = self.check(j)
            self.assertFalse(ok, want)
            self.assertEqual(why, want)

    def test_type_filter_per_selection(self):
        w2_post = job(employment="CONTRACT", extra={"dice_types": ["Contract W2"]},
                      description="Remote contract on W2. React, Node.js.")
        c2c_post = job()
        t1099_post = job(employment="CONTRACT", extra={"dice_types": ["Contract Independent"]},
                         description="Remote 1099 contract. React.")
        silent = job(employment="CONTRACT", description="Remote contract. React and Node.js.")
        c2c_only, w2_only, t1099 = self.typed("contract_c2c"), self.typed("contract_w2"), self.typed("contract_1099")
        self.assertFalse(filters.check(w2_post, c2c_only)[0])
        self.assertTrue(filters.check(w2_post, w2_only)[0])
        self.assertEqual(filters.employment_type(w2_post, w2_only), "contract_w2")
        self.assertFalse(filters.check(c2c_post, w2_only)[0])
        self.assertTrue(filters.check(c2c_post, c2c_only)[0])
        self.assertFalse(filters.check(t1099_post, c2c_only)[0])
        self.assertTrue(filters.check(t1099_post, t1099)[0])
        sponsor_1099 = self.typed("contract_1099", "contract_c2c", **{"work_authorization.needs_sponsorship": True})
        self.assertFalse(filters.check(t1099_post, sponsor_1099)[0])
        for prof in (c2c_only, w2_only, t1099):  # not stated: kept, label empty (Not stated)
            self.assertTrue(filters.check(silent, prof)[0])
            self.assertEqual(filters.employment_type(silent, prof), "")
        both = job(employment="CONTRACT", description="Remote. C2C or W2 both fine. React.")
        self.assertEqual(filters.employment_type(both, self.typed("contract_w2", "contract_c2c")), "contract_c2c")
        self.assertEqual(filters.employment_type(both, w2_only), "contract_w2")

    def test_rate_filter(self):
        self.assertEqual(filters.hourly_rate(job(description="Rate: $90/hr on C2C.")), (90.0, 90.0))
        self.assertEqual(filters.hourly_rate(job(pay="$80-95")), (80.0, 95.0))
        self.assertIsNone(filters.hourly_rate(job(pay="$150000-180000")))
        self.assertTrue(self.check(job(pay="$80-95"))[0])  # top of range clears the 85 floor
        self.assertTrue(self.check(job(pay=""))[0])        # no rate posted: kept
        no_floor = self.typed("contract_c2c", **{"pay.hourly_floor": 0})
        self.assertTrue(filters.check(job(pay="$40-50"), no_floor)[0])
        _, info = filters.score(job(pay="$80-95"), self.prof)
        self.assertEqual(info["terms"], "$80-95/hr, C2C confirmed, remote")

    def test_remote_outside_us_dropped(self):
        j = job(remote=None, employment="CONTRACT", description="C2C. Remote - Canada only. React and Node.")
        self.assertEqual(self.check(j), (False, "remote outside US"))

    def test_hybrid_in_text_when_remote_unknown(self):
        j = job(remote=None, employment="CONTRACT", description="C2C role, remote with hybrid days in Dallas.")
        self.assertEqual(self.check(j), (False, "hybrid/onsite"))

    def test_gc_usc_only_depends_on_sponsorship(self):
        j = job(description="Remote C2C. USC/GC only. React, Node.js, Python.")
        self.assertTrue(self.check(j)[0])
        ok, why = self.check(j, self.sponsor)
        self.assertFalse(ok)
        self.assertIn("visa holders", why)

    def test_citizens_only_depends_on_citizenship(self):
        j = job(description="Remote C2C. US citizens only. React, Node.js.")
        self.assertTrue(self.check(j)[0])
        gc = settings.from_profile(profile(**{"work_authorization.citizenship": "Canada"}))
        self.assertEqual(self.check(j, gc), (False, "US citizens only"))

    def test_clearance_skip_can_be_turned_off(self):
        p = settings.from_profile(profile(**{"c2c.skip_clearance": False}))
        j = job(description="Remote. Public trust clearance. React and Node.")
        self.assertTrue(filters.check(j, p)[0])

    def test_c2c_status(self):
        self.assertEqual(filters.c2c_status(job(employment="CONTRACT", description="Open to H1B and GC-EAD.")), "likely")
        self.assertEqual(filters.c2c_status(job(employment="CONTRACT", description="Corp to corp is fine.")), "yes")
        self.assertEqual(filters.c2c_status(job(employment="CONTRACT", description="Contract role.")), "unknown")
        self.assertEqual(filters.c2c_status(job(title="React Dev (W2)", employment="CONTRACT", description="")), "no")

    def test_years_asked_takes_largest_experience_bar(self):
        self.assertEqual(filters.years_asked("2+ years of AI experience, 8+ years of software development"), 8)
        self.assertIsNone(filters.years_asked("Our company has 20 years in business."))


TRACKER_HEADER = ("Job Title,Company,Location,Job Link,Pay Scale,Apply Status,Applied Date,Job Posted At,Notes,"
                  "Match Score,Source,Employment Type,Application Issues,Job Description,Outcome / Next Step,"
                  "Reason Tag,H-1B Evidence,Reached Interview,Rate / Terms,Priority,Recruiter Email,"
                  "Recruiter Name / LinkedIn,Resume to Send,Email Subject,Email Body,LinkedIn Note,Contacted On,"
                  "Follow-up 1,Follow-up 2")


def tracker_row(title, company, link, etype, contacted=""):
    cells = [""] * 29
    cells[0], cells[1], cells[3], cells[5], cells[11], cells[26] = title, company, link, "Shortlisted", etype, contacted
    return dict(zip(TRACKER_HEADER.split(","), cells))


class ShortlistTest(unittest.TestCase):
    def mixed_tracker(self):
        return [
            tracker_row("Senior React Developer", "Old Vendor LLC", "https://www.dice.com/job-detail/a", "Contract (C2C)"),
            tracker_row("Python Engineer", "Beta Corp", "https://jobs.ashbyhq.com/beta/zz", "Full-time"),
            tracker_row("Platform Engineer", "Delta Solutions", "https://dice.com/x", "Contract (C2C)",
                        contacted=date.today().isoformat()),
            tracker_row("Backend Engineer", "Hotel", "https://boards.greenhouse.io/hotel/jobs/123", "Full-time"),
        ]

    def test_dedupe_against_mixed_tracker(self):
        jobs = [
            {"Score": "90", "Title": "Lead Engineer", "Company": "Gamma", "Link": "https://www.dice.com/job-detail/a?src=x"},
            {"Score": "88", "Title": "Python Engineer", "Company": "BETA, Inc.", "Link": "https://dice.com/b"},  # full-time row
            {"Score": "86", "Title": "AI Engineer", "Company": "Delta", "Link": "https://dice.com/c"},  # contacted today
            {"Score": "84", "Title": "Backend Engineer", "Company": "Hotel", "Link": "https://dice.com/i"},  # full-time row
            {"Score": "80", "Title": "Full Stack Dev", "Company": "Echo", "Link": "https://dice.com/d"},
            {"Score": "92", "Title": "Senior Full Stack", "Company": "Echo LLC", "Link": "https://dice.com/e"},
            {"Score": "75", "Title": "Node Developer", "Company": "Echo", "Link": "https://dice.com/f"},
            {"Score": "60", "Title": "React Dev", "Company": "Foxtrot", "Link": "https://dice.com/g"},
            {"Score": "71", "Title": "React Dev", "Company": "Golf", "Link": "https://dice.com/h"},
        ]
        rows, dropped = shortlist.shortlist(jobs, self.mixed_tracker(), ["Nobody"], min_score=70)
        self.assertEqual([r["Link"] for r in rows], ["https://dice.com/e", "https://dice.com/h"])
        self.assertEqual(dropped, {"already in tracker": 3, "company contacted today": 1, "below min score": 1,
                                   "second role at same company": 2})

    def test_extra_contacted_and_norm(self):
        rows, d = shortlist.shortlist([{"Score": "90", "Title": "X Dev", "Company": "Acme Inc", "Link": "u1"}], [],
                                      ["ACME Technologies"])
        self.assertEqual((rows, d["company contacted today"]), ([], 1))
        self.assertEqual(shortlist.norm("Acme Technologies, Inc."), shortlist.norm("ACME"))

    def test_url_key_across_forms(self):
        self.assertEqual(shortlist.url_key("https://www.linkedin.com/jobs/view/4012345678/?trk=x"),
                         shortlist.url_key("https://linkedin.com/jobs/search/?currentJobId=4012345678"))

    def test_cli_writes_shortlist_and_29_column_rows(self):
        with tempfile.TemporaryDirectory() as d:
            jp, tp, op, rp = (os.path.join(d, n) for n in ("c2c_jobs.csv", "tracker.csv", "out.csv", "rows.tsv"))
            with open(jp, "w") as f:
                f.write("Score,C2C,Employment Type,Rate / Terms,Title,Company,Location,Tier,Source,Posted,Pay,"
                        "Years asked,Skills matched,Link\n"
                        "90,yes,Contract (C2C),\"C2C confirmed, remote\",Senior React Dev,Zeta,Remote (US),,dice,"
                        "2026-01-02,,5,\"react, node.js\",https://www.dice.com/job-detail/2\n"
                        "80,unknown,Not stated,C2C not stated,React Dev,Acme,Remote (US),,dice,2026-01-02,,,"
                        "react,https://www.dice.com/job-detail/1\n")
            with open(tp, "w") as f:
                f.write(TRACKER_HEADER + "\n")
                f.write("Senior Engineer,Acme,Remote,https://www.dice.com/job-detail/1,,Applied" + "," * 23 + "\n")
            with open(os.path.join(d, "raw_jobs_x.json"), "w") as f:
                json.dump([{"url": "https://www.dice.com/job-detail/2", "description": "React and Node.js."}], f)
            shortlist.main(["--jobs", jp, "--tracker", tp, "--out", op, "--rows-out", rp])
            with open(op) as f:
                out = f.read()
            self.assertIn("Zeta", out)
            self.assertNotIn("Acme", out)
            with open(rp) as f:
                lines = list(csv.reader(f, delimiter="\t"))
            self.assertEqual(lines[0], TRACKER_HEADER.split(","))
            row = lines[1]
            self.assertEqual(len(row), 29)
            self.assertEqual(row[11], "Contract (C2C)")
            self.assertEqual((row[0], row[1], row[3], row[5]), ("Senior React Dev", "Zeta",
                                                                 "https://www.dice.com/job-detail/2", "Shortlisted"))
            self.assertEqual((row[9], row[10], row[13], row[14]), ("90", "Dice", "React and Node.js.", "Not contacted"))
            self.assertIn("years asked: 5", row[8])
            self.assertEqual((row[18], row[19]), ("C2C confirmed, remote", "A"))
            self.assertEqual(row[23:26], ["", "", ""])  # drafts come later from build_outreach
            self.assertIn("WORKDAY(AA3,3)", row[27])  # tracker has 1 data row -> first new row is 3
            with open(os.path.join(d, "rows.json")) as f:
                self.assertEqual(json.load(f)[0][:4], row[:4])  # same rows for check_dupes.py


class EmailTest(unittest.TestCase):
    DESC = ("We need a Senior Full Stack Engineer. Must have: React and TypeScript, Node.js REST APIs, "
            "PostgreSQL. Hybrid, 2 days a week in office. Nice to have: Kafka, Azure.")

    def setUp(self):
        self.p = profile(**{"c2c.outreach": {"closing": "", "proof": {
            "react": "at Acme Analytics, rebuilt the reporting UI in React",
            "node": "own Node.js services on PostgreSQL",
            "sql": {"proof": "tuned PostgreSQL queries for the main dashboard", "label": "SQL"},
        }}})

    def test_compose_uses_config_and_skips_sensitive_lines(self):
        subj, body, chosen = emails.compose(self.p, "Senior Full Stack Engineer (Remote)", self.DESC, "dice", "Sam")
        self.assertTrue(subj.startswith("Senior Full Stack Engineer – Jane Doe"))
        self.assertIn("Hi Sam,", body)
        self.assertIn("I applied on Dice", body)
        self.assertIn("I'm a senior full-stack engineer, currently at Acme Analytics.", body)
        self.assertIn("rebuilt the reporting UI in React.", body)
        self.assertIn("Is this fully remote", body)
        phone = self.p["identity"]["phone"]
        self.assertTrue(body.rstrip().endswith(f"Jane Doe\n{phone} · linkedin.com/in/janedoe-example"))
        self.assertNotIn("Azure", body)  # nice-to-have only
        self.assertNotIn(emails.PLACEHOLDER, body)
        low = body.lower()
        for word in VISA + ("$", "/hr", "rate", "austin"):
            self.assertNotIn(word, low)
        self.assertEqual(len(chosen), 3)

    def test_placeholder_when_no_proof(self):
        p = fixture()
        _, body, chosen = emails.compose(p, "AI Engineer", "Build RAG with LLMs and AI agents.", "linkedin")
        self.assertIn(emails.PLACEHOLDER, body)
        self.assertIn("Hi there,", body)
        self.assertIn("I applied on LinkedIn", body)

    def test_first_name_only_when_certain(self):
        self.assertEqual(emails.first_name("sam.lee@vendor.com"), "Sam")
        self.assertEqual(emails.first_name("slee@vendor.com"), "")
        self.assertEqual(emails.first_name("jobs@vendor.com"), "")
        self.assertEqual(emails.first_name("slee@vendor.com", "Samantha Lee"), "Samantha")
        self.assertEqual(emails.email_kind("careers@vendor.com"), "ATS inbox")
        self.assertEqual(emails.email_kind("sam.lee@vendor.com"), "Recruiter (named)")

    def test_outreach_rows(self):
        jobs = [{"Score": "90", "C2C": "yes", "Employment Type": "Contract (C2C)", "Rate / Terms": "C2C confirmed",
                 "Title": "Senior AI Engineer", "Company": "Acme", "Location": "Remote (US)", "Source": "dice",
                 "Posted": "2026-01-02", "Link": "https://dice.com/1"},
                {"Score": "75", "C2C": "unknown", "Employment Type": "Not stated", "Title": "Python Developer",
                 "Company": "Beta", "Source": "linkedin", "Link": "https://dice.com/2"}]
        contacts = {"https://dice.com/2": {"Apply email": "jobs@beta.com", "Contract types": "Contract W2"},
                    "https://dice.com/1": {"Apply email": "sam.lee@acme.com"}}
        rows = outreach.build_rows(self.p, jobs, {"https://dice.com/1": "LLM agents and RAG."}, contacts, first_row=10)
        self.assertEqual([len(r) for r in rows], [29, 29])
        a, b = rows
        self.assertEqual((a[11], b[11]), ("Contract (C2C)", "Not stated"))
        self.assertEqual((a[10], b[10]), ("Dice", "LinkedIn"))
        self.assertEqual((a[18], a[19], a[20], a[21]), ("C2C confirmed", "A", "sam.lee@acme.com", "Sam"))
        self.assertEqual(a[22], "main")  # c2c.resume_versions missing "ai" -> "default" -> resumes[].label "main"
        self.assertTrue(a[23].startswith("Senior AI Engineer – Jane Doe"))
        self.assertIn("Hi Sam,", a[24])
        self.assertLessEqual(len(a[25]), 300)
        self.assertIn("WORKDAY(AA10,3)", a[27])
        self.assertIn("WORKDAY(AA11,5)", b[28])
        self.assertEqual(b[19], "Skip")  # contacts say W2 only; candidate picked C2C only
        self.assertIn("Dice lists only W2", b[18])
        self.assertIn("employment type not stated", b[8])
        self.assertEqual(outreach.HEADER[outreach.S:][0], "Rate / Terms")

    def test_resume_version_fallbacks(self):
        p = profile(**{"c2c.resume_versions": {"ai": "AI_Engineer", "default": "main"}})
        self.assertEqual(outreach.resume_version(p, "Senior AI Engineer"), "Jane_Doe_Resume_AI_Engineer")
        self.assertEqual(outreach.resume_version(p, "Tech Lead"), "main")


if __name__ == "__main__":
    unittest.main()

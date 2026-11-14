"""Search -> shortlist -> apply pipeline: screen helpers, gate, dedupe, ATS filter, row builder, Ashby fill
generator, H-1B module and company-list helpers. No network: fetches are stubbed or never called.
Run: python3 -m unittest discover -s tests (from the repo root)."""
import copy
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "profile.json")
os.environ["JOB_KIT_PROFILE"] = FIXTURE
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from core import config  # noqa: E402

SJ = os.path.join(ROOT, ".claude", "skills", "search-jobs", "scripts")
AB = os.path.join(ROOT, ".claude", "skills", "apply-batch", "scripts")
H1B = os.path.join(ROOT, "modules", "h1b")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


screen = _load("screen", os.path.join(ROOT, "scripts", "screen.py"))
sys.modules["screen"] = screen
gate = _load("jk_gate", os.path.join(AB, "gate.py"))
check_dupes = _load("jk_check_dupes", os.path.join(SJ, "check_dupes.py"))
filter_jobs = _load("jk_filter_jobs", os.path.join(AB, "filter_jobs.py"))
build_rows = _load("jk_build_rows", os.path.join(AB, "build_rows.py"))
make_fill_js = _load("jk_make_fill_js", os.path.join(AB, "make_fill_js.py"))
company_list = _load("jk_company_list", os.path.join(SJ, "company_list.py"))
h1b_lookup = _load("jk_h1b_lookup", os.path.join(H1B, "h1b_lookup.py"))
sources = _load("jk_sources", os.path.join(SJ, "sources.py"))

LONG = " We build web products for hospitals and logistics teams, and ship weekly." * 30
TS_DESC = "You will build React and TypeScript features with Node.js services on Postgres and AWS." + LONG


def profile(**changes):
    """The Jane Doe fixture with dotted-key overrides, e.g. profile(**{"modules.h1b": True})."""
    p = copy.deepcopy(config.load())
    for k, v in changes.items():
        cur = p
        parts = k.split(".")
        for part in parts[:-1]:
            cur = cur.setdefault(part, {})
        cur[parts[-1]] = v
    return p


def sponsored(**more):
    return profile(**{"work_authorization.needs_sponsorship": True, "work_authorization.citizenship": "India",
                      "work_authorization.any_employer_answer": "No", **more})


class Screen(unittest.TestCase):
    def test_norm_and_dup(self):
        self.assertEqual(screen.norm("Acme, Inc."), "acme")
        rows = [(screen.norm("Acme Inc"), screen.norm("Senior Software Engineer"))]
        self.assertTrue(screen.is_dup(screen.norm("ACME"), screen.norm("Senior Software Engineer"), rows))
        self.assertFalse(screen.is_dup(screen.norm("Acme"), screen.norm("Data Scientist"), rows))

    def test_sponsor_regexes(self):
        self.assertTrue(screen.SPONSOR_BLOCK.search("We are unable to sponsor visas for this role."))
        self.assertTrue(screen.SPONSOR_BLOCK.search("Must be authorized to work without current or future sponsorship"))
        self.assertTrue(screen.SPONSOR_BLOCK.search("U.S. persons only"))
        self.assertFalse(screen.SPONSOR_BLOCK.search("We offer great benefits and visa sponsorship is available."))
        self.assertTrue(screen.SPONSOR_OK.search("H-1B transfer welcome"))

    def test_no_sponsor_list_only_with_h1b_module(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "profile"))
            with open(os.path.join(d, "profile", "no_sponsor_companies.txt"), "w") as fh:
                fh.write("# header\nGlobex Inc  # 2026-01-01: rejection email\n")
            with mock.patch.dict(os.environ, {"JOB_KIT_DATA": d}):
                screen._NS_CACHE.clear()
                self.assertFalse(screen.is_no_sponsor("Globex", profile()))
                self.assertTrue(screen.is_no_sponsor("Globex", profile(**{"modules.h1b": True})))
                self.assertFalse(screen.is_no_sponsor("Initech", profile(**{"modules.h1b": True})))
            screen._NS_CACHE.clear()

    def test_employment_type_detection(self):
        et = screen.employment_type
        self.assertEqual(et("FullTime"), "full_time")
        self.assertEqual(et("PartTime"), "part_time")
        self.assertEqual(et("Contract", "Engineer", "Open to corp-to-corp."), "contract_c2c")
        self.assertEqual(et("", "Senior Engineer (Contract)", "W2 only"), "contract_w2")
        self.assertEqual(et("", "Engineer", "This is a 6-month contract role."), "contract")
        self.assertEqual(et("", "Smart Contract Engineer", "A full-time role."), "full_time")
        self.assertEqual(et("", "Engineer", "This is a part-time position, 20 hours a week."), "part_time")
        self.assertEqual(et("Intern"), "intern")
        self.assertEqual(et("", "Engineer", "Build things."), "")

    def test_type_decision(self):
        p = profile()  # fixture wants full_time + contract_c2c
        self.assertEqual(screen.type_decision("full_time", p), (True, "Full-time", ""))
        self.assertEqual(screen.type_decision("contract_c2c", p), (True, "Contract (C2C)", ""))
        self.assertFalse(screen.type_decision("part_time", p)[0])
        self.assertFalse(screen.type_decision("contract_w2", p)[0])
        self.assertEqual(screen.type_decision("contract", p)[:2], (True, "Not stated"))
        self.assertEqual(screen.type_decision("", p), (True, "Not stated", "employment type not stated"))
        ft_only = profile(**{"targets.employment_types": ["full_time"]})
        self.assertFalse(screen.type_decision("contract", ft_only)[0])
        self.assertTrue(screen.type_decision("part_time", profile(**{"targets.employment_types": ["full_time", "part_time"]}))[0])
        self.assertFalse(screen.type_decision("intern", p)[0])

    def test_hourly_top(self):
        self.assertEqual(screen.hourly_top("$70 - $90/hr"), 90.0)
        self.assertEqual(screen.hourly_top("$85 per hour, C2C"), 85.0)
        self.assertIsNone(screen.hourly_top("$150K - $190K"))

    def test_okloc_and_onsite_elsewhere(self):
        p = profile()
        self.assertTrue(screen.okloc("Austin, TX", p))
        self.assertTrue(screen.okloc("Remote", p))
        self.assertFalse(screen.okloc("Seattle, WA", p))
        self.assertTrue(screen.onsite_elsewhere("This role is on-site in Seattle five days a week.", p))
        self.assertEqual(screen.onsite_elsewhere("On-site in Austin.", p), "")
        self.assertEqual(screen.onsite_elsewhere("On-site in Seattle.", profile(**{"locations.relocation_anywhere_us": True})), "")


class Gate(unittest.TestCase):
    def g(self, title="Senior Software Engineer", desc=TS_DESC, loc="Austin, TX", comp="$170K - $210K", p=None, **kw):
        return gate.gate(title, desc, loc, comp, p=p or profile(), **kw)

    def test_good_posting_passes(self):
        r = self.g()
        self.assertEqual(r["verdict"], "PASS", r)
        self.assertEqual(r["primary_stack"], "primary")

    def test_no_sponsorship_only_matters_when_needed(self):
        desc = TS_DESC + " We do not offer visa sponsorship."
        self.assertEqual(self.g(desc=desc)["fails"], [])
        self.assertIn("states no sponsorship", self.g(desc=desc, p=sponsored())["fails"])

    def test_citizenship_and_clearance(self):
        desc = TS_DESC + " US citizenship required."
        self.assertNotIn("citizenship required", self.g(desc=desc)["fails"])  # the fixture candidate is a citizen
        self.assertIn("citizenship required", self.g(desc=desc, p=sponsored())["fails"])
        r = self.g(desc=TS_DESC + " An active Top Secret clearance is required.")
        self.assertIn("security clearance required", r["fails"])
        self.assertEqual(r["fails"].count("security clearance required"), 1)
        held = profile(**{"work_authorization.security_clearance": "TS/SCI"})
        self.assertNotIn("security clearance required", self.g(desc=TS_DESC + " Top Secret clearance.", p=held)["fails"])

    def test_level_years_pay(self):
        self.assertTrue(any("skip_levels" in f for f in self.g(title="Staff Software Engineer")["fails"]))
        self.assertTrue(any("years of experience asked" in f for f in self.g(desc=TS_DESC + " 12+ years of software experience.")["fails"]))
        self.assertTrue(any("years asked" in w for w in self.g(desc=TS_DESC + " 9+ years of experience.")["warns"]))
        self.assertTrue(any("pay tops out" in f for f in self.g(comp="$110K - $140K")["fails"]))
        self.assertEqual(self.g(comp="Not listed")["fails"], [])

    def test_stack_knockouts(self):
        net = "Our platform is built on .NET and C# with SQL Server." + LONG
        p = profile(**{"targets.other_stack_knockouts": [{"regex": r"\.net\b|\bc#", "label": ".NET/C#"}]})
        self.assertTrue(any(".NET/C#" in f for f in self.g(desc=net, p=p)["fails"]))
        r = self.g(desc=net + " The front end is React and TypeScript.", p=p)
        self.assertEqual(r["fails"], [])
        self.assertTrue(any(".NET/C#" in w for w in r["warns"]))
        self.assertIn("primary stack not mentioned", self.g(desc="Great team." + LONG)["warns"])

    def test_locations(self):
        self.assertTrue(any("outside the US" in f for f in self.g(loc="London, United Kingdom")["fails"]))
        self.assertTrue(any("outside the candidate's areas" in f for f in self.g(loc="Seattle, WA")["fails"]))
        self.assertEqual(self.g(loc="Remote (US)")["fails"], [])
        anywhere = profile(**{"locations.relocation_anywhere_us": True})
        self.assertEqual(self.g(loc="Seattle, WA", p=anywhere)["fails"], [])
        self.assertTrue(any("outside the US" in f for f in self.g(loc="Toronto, Canada", p=anywhere)["fails"]))
        r = self.g(loc="Remote", desc=TS_DESC + " Candidates must reside in one of the following states: NY, NJ.")
        self.assertTrue(any("check TX is eligible" in w for w in r["warns"]))

    def test_domain_skip_and_no_sponsor_list(self):
        p = profile(**{"targets.domain_skips": [{"regex": r"\bcrypto\b", "label": "crypto"}]})
        self.assertIn("domain skip: crypto", self.g(desc=TS_DESC + " We build crypto wallets.", p=p)["fails"])
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "profile"))
            open(os.path.join(d, "profile", "no_sponsor_companies.txt"), "w").write("Globex\n")
            with mock.patch.dict(os.environ, {"JOB_KIT_DATA": d}):
                screen._NS_CACHE.clear()
                r = self.g(company="Globex", p=sponsored(**{"modules.h1b": True}))
                self.assertTrue(any("does not sponsor" in f for f in r["fails"]))
                self.assertEqual(self.g(company="Globex")["fails"], [])
            screen._NS_CACHE.clear()

    def test_work_type_and_hourly(self):
        self.assertTrue(any("work type not wanted" in f for f in self.g(employment="Part-time")["fails"]))
        self.assertEqual(self.g(employment="Contract (C2C)", comp="$95/hr")["fails"], [])
        self.assertTrue(any("work type not wanted" in f for f in self.g(employment="Contract (W2)")["fails"]))
        self.assertTrue(any("below $85/hr" in f for f in self.g(employment="Contract (C2C)", comp="$60 - $70/hr")["fails"]))
        self.assertIn("contract; W2/C2C/1099 not stated", self.g(desc=TS_DESC + " This is a 6-month contract role.")["warns"])
        self.assertEqual(self.g(employment="Not stated")["verdict"], "PASS")
        self.assertEqual(gate.score("SWE", TS_DESC, comp="$110/hr", p=profile())["pay"], 5)

    def test_score(self):
        p = profile()
        s = gate.score("Senior Software Engineer", TS_DESC + " 5+ years of experience.", "Austin, TX", "$170K - $210K", p=p)
        self.assertEqual(s["stack"], 30)
        self.assertEqual(s["sponsorship"], 15)  # doesn't need sponsorship: full marks
        self.assertEqual(s["seniority"], 10)
        self.assertEqual(s["location"], 10)
        self.assertEqual(s["pay"], 5)
        self.assertIn("react", s["tools_hit"])
        self.assertEqual(s["total"], sum(v for k, v in s.items() if k not in ("total", "tools_hit")))
        sp = sponsored()
        self.assertEqual(gate.score("SWE", TS_DESC, p=sp, h1b_verdict="sponsors")["sponsorship"], 15)
        self.assertEqual(gate.score("SWE", TS_DESC, p=sp, h1b_verdict="none")["sponsorship"], 3)
        self.assertEqual(gate.score("SWE", TS_DESC, p=sp, h1b_verdict="none", large_company=True)["sponsorship"], 0)
        self.assertEqual(gate.score("SWE", TS_DESC, p=sp)["sponsorship"], 6)

    def test_run_sorts_by_h1b_tier(self):
        stub = {"lookup": lambda co: {"verdict": {"A": "none", "B": "sponsors"}[co], "count_recent": 0},
                "evidence": lambda h: h["verdict"]}
        items = [("A", "Senior Software Engineer", TS_DESC, "Austin, TX", "", {}),
                 ("B", "Senior Software Engineer", "Python." + LONG, "Austin, TX", "", {})]
        out = gate.run(items, sponsored(**{"modules.h1b": True}), stub)
        self.assertEqual([g["company"] for g in out], ["B", "A"])
        self.assertEqual(out[1]["verdict"], "WARN")


class CheckDupes(unittest.TestCase):
    def test_url_key(self):
        self.assertEqual(check_dupes.url_key("https://www.linkedin.com/jobs/view/4455478729/"),
                         check_dupes.url_key("https://www.linkedin.com/jobs/view/senior-eng-at-acme-4455478729/?trk=x"))
        self.assertEqual(check_dupes.url_key("https://x.com/jobs?gh_jid=123456"), "123456")

    def test_check(self):
        existing = [("Senior Full-Stack Engineer", "Acme Inc", "https://jobs.example/acme/1", "Shortlisted"),
                    ("Product Engineer, Growth", "Globex", "https://jobs.example/globex/9", "Applied")]
        rows = [["Full Stack Engineer", "ACME", "", "https://other.example/2"],
                ["Software Engineer", "Initech", "", "https://jobs.example/acme/1"],
                ["Growth Product Designer, Analytics Platform", "Globex", "", "https://jobs.example/globex/10"],
                ["Backend Engineer", "Hooli", "", "https://jobs.example/hooli/1"]]
        bad, warn = check_dupes.check(rows, existing)
        self.assertEqual([b[0] for b in bad], [1, 2])
        self.assertEqual([w[0] for w in warn], [3])

    def test_cross_type_and_header_export(self):
        with tempfile.TemporaryDirectory() as d:
            tr = os.path.join(d, "tracker.csv")
            hdr = open(os.path.join(ROOT, "scripts", "tracker_header.md")).read().split("```")[1].strip().split("\t")
            self.assertEqual(len(hdr), 29)
            import csv as _csv
            with open(tr, "w", newline="") as f:
                w = _csv.writer(f)
                w.writerow(hdr)
                row = [""] * 29
                row[0], row[1], row[3], row[5], row[11] = "Senior Full Stack Engineer", "Acme", "https://dice.example/j/77", "Shortlisted", "Contract (C2C)"
                w.writerow(row)
                w.writerow(["Product Engineer", "Hooli", "", "https://h.example/1", "", "Applied"])  # older, short export row
            got = check_dupes.load_tracker(tr)
            self.assertEqual(got[0], ("Senior Full Stack Engineer", "Acme", "https://dice.example/j/77", "Shortlisted, Contract (C2C)"))
            self.assertEqual(got[1][3], "Applied")
            rows = os.path.join(d, "rows.json")
            json.dump([["Senior Full-Stack Engineer", "Acme Inc", "", "https://jobs.ashbyhq.com/acme/1"] + [""] * 7 + ["Full-time"]], open(rows, "w"))
            self.assertEqual(check_dupes.main(["--rows", rows, "--tracker", tr]), 1)  # same role, other work type

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            tr = os.path.join(d, "tracker.csv")
            with open(tr, "w") as f:
                f.write("Job Title,Company,Location,Job Link,Pay Scale,Apply Status\n"
                        "Senior Software Engineer,Acme,Austin,https://a.example/1,,Applied\n")
            rows = os.path.join(d, "rows.json")
            json.dump([["Senior Software Engineer", "Acme", "", "https://b.example/2"]], open(rows, "w"))
            self.assertEqual(check_dupes.main(["--rows", rows, "--tracker", tr]), 1)
            json.dump([["Product Engineer", "Hooli", "", "https://b.example/3"]] * 2, open(rows, "w"))
            self.assertEqual(check_dupes.main(["--rows", rows, "--tracker", tr]), 1)  # duplicate inside the batch
            json.dump([["Product Engineer", "Hooli", "", "https://b.example/3"]], open(rows, "w"))
            self.assertEqual(check_dupes.main(["--rows", rows, "--tracker", tr]), 0)


def ashby_job(title, loc, date="2026-11-05", desc=TS_DESC, comp="", remote=False, url=None):
    return {"title": title, "location": loc, "secondaryLocations": [], "publishedAt": date + "T00:00:00Z",
            "descriptionPlain": desc, "compensation": {"compensationTierSummary": comp}, "isRemote": remote,
            "jobUrl": url or f"https://jobs.ashbyhq.com/x/{abs(hash((title, loc))) % 10**8}"}


class FilterJobs(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        boards = {"acme": [ashby_job("Senior Software Engineer", "Austin, TX"),
                           ashby_job("Senior Software Engineer", "Austin, TX")],  # same role twice: dup_run
                  "globex": [ashby_job("Product Engineer", "Remote", remote=True, desc=TS_DESC + " We cannot sponsor visas.")],
                  "initech": [ashby_job("Senior Full Stack Engineer", "Seattle, WA"),
                              ashby_job("Engineering Manager", "Austin, TX"),
                              ashby_job("Senior Software Engineer", "Dallas, TX", date="2026-09-01"),
                              ashby_job("Senior Software Engineer II", "London", remote=False)],
                  "hooli": [ashby_job("Full Stack Engineer", "Austin, TX", comp="$90K – $120K")],
                  "umbrella": [ashby_job("Senior Software Engineer", "Dallas, TX", url="https://jobs.ashbyhq.com/umbrella/1")]}
        json.dump(boards, open(os.path.join(self.d, "ashby_boards.json"), "w"))
        json.dump({"pied": [{"title": "Senior Software Engineer", "location": {"name": "Austin, TX"},
                             "absolute_url": "https://boards.greenhouse.io/pied/jobs/1", "first_published": "2026-11-06",
                             "content": "&lt;p&gt;React and TypeScript&lt;/p&gt;"}]},
                  open(os.path.join(self.d, "gh_boards.json"), "w"))

    def tearDown(self):
        shutil.rmtree(self.d)

    def run_filter(self, p):
        f = filter_jobs.Filter(p, "2026-11-01", [(screen.norm("Umbrella"), screen.norm("Staff Engineer"))],
                               {"https://jobs.ashbyhq.com/umbrella/1"})
        return f, filter_jobs.run(f, self.d)

    def test_profile_filters(self):
        f, out = self.run_filter(profile())
        kept = sorted((o["co"], o["title"]) for o in out)
        self.assertEqual(kept, [("acme", "Senior Software Engineer"), ("globex", "Product Engineer"),
                                ("pied", "Senior Software Engineer")])
        for k in ("dup_run", "loc", "title", "old", "pay_below_floor", "dup_tracker"):
            self.assertGreaterEqual(f.stats.get(k, 0), 1, (k, f.stats))
        self.assertNotIn("sponsor", f.stats)

    def test_employment_type_filter(self):
        boards = json.load(open(os.path.join(self.d, "ashby_boards.json")))
        boards["parttime"] = [dict(ashby_job("Senior Software Engineer", "Austin, TX"), employmentType="PartTime")]
        boards["c2c"] = [dict(ashby_job("Senior Software Engineer", "Remote", remote=True, comp="$95/hr",
                                        desc=TS_DESC + " Corp-to-corp welcome."), employmentType="Contract")]
        boards["w2"] = [dict(ashby_job("Senior Full Stack Engineer", "Remote", remote=True, desc=TS_DESC + " W2 only."), employmentType="Contract")]
        boards["cheap"] = [dict(ashby_job("Product Engineer", "Remote", remote=True, comp="$50/hr", desc=TS_DESC + " C2C."), employmentType="Contract")]
        json.dump(boards, open(os.path.join(self.d, "ashby_boards.json"), "w"))
        json.dump({"tiny": [{"text": "Senior Software Engineer", "categories": {"commitment": "Part-time", "location": "Austin, TX"},
                             "hostedUrl": "https://jobs.lever.co/tiny/1", "createdAt": 1793923200000, "descriptionPlain": TS_DESC}]},
                  open(os.path.join(self.d, "lever_boards.json"), "w"))
        f, out = self.run_filter(profile())
        by = {o["co"]: o for o in out}
        self.assertNotIn("parttime", by)
        self.assertNotIn("tiny", by)
        self.assertNotIn("w2", by)
        self.assertNotIn("cheap", by)
        self.assertEqual(by["c2c"]["emp_label"], "Contract (C2C)")
        self.assertEqual(by["acme"]["emp_label"], "Not stated")
        self.assertEqual(f.stats["employment_type"], 3)
        self.assertEqual(f.stats["pay_below_hourly_floor"], 1)
        f, out = self.run_filter(profile(**{"targets.employment_types": ["full_time", "part_time"]}))
        names = [o["co"] for o in out]
        self.assertIn("parttime", names)
        self.assertIn("tiny", names)
        self.assertNotIn("c2c", names)

    def test_sponsorship_drop_only_when_needed(self):
        f, out = self.run_filter(sponsored())
        self.assertEqual(f.stats.get("sponsor"), 1)
        self.assertNotIn("globex", [o["co"] for o in out])

    def test_relocation_anywhere(self):
        f, out = self.run_filter(profile(**{"locations.relocation_anywhere_us": True}))
        self.assertIn("initech", [o["co"] for o in out])  # Seattle passes
        self.assertNotIn("London", [o["loc"] for o in out])

    def test_cli(self):
        r = subprocess.run([sys.executable, os.path.join(AB, "filter_jobs.py"), "--run-dir", self.d, "--cutoff", "2026-11-01"],
                           capture_output=True, text=True, env={**os.environ, "JOB_KIT_PROFILE": FIXTURE})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("dedupe against the sheet is OFF", r.stdout)
        self.assertTrue(os.path.exists(os.path.join(self.d, "kept.json")))


class BuildRows(unittest.TestCase):
    KEPT = [{"src": "Ashby", "co": "acme", "title": "Senior Software Engineer", "url": "https://jobs.ashbyhq.com/acme/1",
             "date": "2026-11-05", "comp": "$170K", "desc": "<p>Build things</p>", "emp_label": "Full-time", "emp_note": ""}]
    PICKS = [{"co": "acme", "title": "senior software", "name": "Acme", "loc": "Austin, TX (Hybrid)", "score": 88,
              "resume": "main", "note": "direct React match; gap: none"}]

    def test_rows_without_h1b(self):
        rows = build_rows.build(self.KEPT, self.PICKS, "2026-11-08", profile())
        self.assertEqual(len(rows[0]), 29)  # A..AC
        self.assertEqual(rows[0][11], "Full-time")
        self.assertEqual(rows[0][17:], [""] * 12)
        self.assertEqual(rows[0][5], "Shortlisted")
        self.assertEqual(rows[0][8], "BATCH 2026-11-08 #1 | resume: main | direct React match; gap: none")
        self.assertEqual(rows[0][10], "Ashby — official company careers")
        self.assertEqual(rows[0][13], "Build things")
        self.assertEqual(rows[0][16], "")

    def test_rows_with_h1b_and_sponsorship(self):
        rows = build_rows.build(self.KEPT, self.PICKS, "2026-11-08", sponsored(**{"modules.h1b": True}),
                                h1b=lambda name: f"sponsors: 9 filings ({name})")
        self.assertTrue(rows[0][8].endswith("; sponsorship not stated"))
        self.assertEqual(rows[0][16], "sponsors: 9 filings (Acme)")

    def test_employment_label_and_note(self):
        kept = [dict(self.KEPT[0], emp_label="Not stated", emp_note="contract; W2/C2C/1099 not stated")]
        r = build_rows.build(kept, self.PICKS, "2026-11-08", profile())[0]
        self.assertEqual(r[11], "Not stated")
        self.assertTrue(r[8].endswith("; contract; W2/C2C/1099 not stated"))
        r = build_rows.build(kept, [dict(self.PICKS[0], type="contract_c2c")], "2026-11-08", profile())[0]
        self.assertEqual(r[11], "Contract (C2C)")
        self.assertNotIn("not stated", r[8])
        r = build_rows.build([{k: v for k, v in self.KEPT[0].items() if not k.startswith("emp_")}], self.PICKS, "2026-11-08", profile())[0]
        self.assertEqual(r[11], "Not stated")
        self.assertIn("employment type not stated", r[8])

    def test_ambiguous_pick_exits(self):
        with self.assertRaises(SystemExit):
            build_rows.build(self.KEPT, [dict(self.PICKS[0], title="nope")], "2026-11-08", profile())


class MakeFillJs(unittest.TestCase):
    def test_render_from_profile(self):
        js = make_fill_js.render(profile())
        self.assertNotIn("__V__", js)
        self.assertNotIn("__YN__", js)
        self.assertIn('"email": "jane.doe@example.com"', js)
        self.assertIn("[/sponsor|visa/i, 'No']", js)
        self.assertIn("austin", js)
        self.assertNotIn("relocat", js.split("const ynRules")[1].split("];")[0])

    def test_sponsorship_and_relocation_flip(self):
        js = make_fill_js.render(sponsored(**{"locations.relocation_anywhere_us": True}))
        self.assertIn("[/sponsor|visa/i, 'Yes']", js)
        self.assertIn("[/without (any )?restriction|for any employer/i, 'No']", js)
        self.assertIn("(open to relocation)", js)
        self.assertIn("relocat/i, 'Yes'", js)

    def test_js_regex_escaping(self):
        self.assertEqual(make_fill_js.js_regex("(?i)a/b"), r"a\/b")

    def test_generated_js_parses(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node not installed")
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "ashby_fill.js")
            self.assertEqual(make_fill_js.main(["--out", out]), 0)
            r = subprocess.run([node, "--check", out], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            for s in ("form_snapshot.js", "ashby_presubmit.js"):
                r = subprocess.run([node, "--check", os.path.join(ROOT, "scripts", s)], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, s + r.stderr)


    def test_screening_answers_and_ask_left_out(self):
        p = profile()
        js = make_fill_js.render(p)
        yn = js.split("const ynRules")[1].split("];")[0]
        self.assertIn("background (check|screen|investigation)/i, 'Yes'", yn)
        self.assertIn("drug (test|screen)/i, 'Yes'", yn)
        self.assertIn("on-?call|night shifts?/i, 'No'", yn)            # weekends_ok = No
        self.assertIn("contract[- ]to[- ]hire/i, 'Yes'", yn)
        self.assertIn("'No', 'verify'", yn)                              # previously employed / relatives
        self.assertNotIn("accommodation", yn)                            # accommodations = "ask"
        self.assertIn('"salaryNow": "Prefer not to say"', js)
        self.assertIn('"languages": "English (Native)"', js)
        self.assertIn('"references": "Available upon request"', js)
        self.assertNotIn("__NEVER__", js)
        ans = {k: v for _, k, v in make_fill_js.form_answers(p)}
        self.assertIsNone(ans["screening.accommodations"])
        left = make_fill_js.left_for_candidate(p)
        self.assertTrue(any("screening.accommodations" in x for x in left))
        self.assertIn("date of birth", left)
        self.assertIn("SSN or national ID number", left)
        self.assertFalse(any("background_check" in x for x in left))
        # an answer switched to "ask" drops its rule and joins the list
        p2 = profile(**{"screening.drug_test_ok": "ask", "screening.current_salary_answer": "ask"})
        js2 = make_fill_js.render(p2)
        self.assertNotIn("drug (test|screen)", js2.split("const ynRules")[1].split("];")[0])
        self.assertIn('"salaryNow": ""', js2)
        self.assertTrue(any("screening.drug_test_ok" in x for x in make_fill_js.left_for_candidate(p2)))

    def test_eeo_and_veteran(self):
        p = profile(**{"eeo.veteran": "I am not a protected veteran", "eeo.veteran_detail": [],
                       "eeo.military_spouse": "No"})
        yn = make_fill_js.render(p).split("const ynRules")[1].split("];")[0]
        self.assertIn("armed forces|military)/i, 'No'", yn)
        self.assertIn("military dependent/i, 'No'", yn)
        p = profile(**{"eeo.veteran_detail": ["Recently separated veteran"]})
        self.assertIn('"veteranDetail": "Recently separated veteran"', make_fill_js.render(p))

    def test_gpa_sharing_rule(self):
        g = make_fill_js.gpa_answer
        self.assertIsNone(g(profile(), required=True))                   # fixture has no GPA
        p = profile(**{"education_summary.gpa": "3.6", "education_summary.share_gpa": "share"})
        self.assertEqual(g(p), "3.6/4.0")
        self.assertEqual(g(p, required=True), "3.6/4.0")
        p = profile(**{"education_summary.gpa": "3.6", "education_summary.share_gpa": "only_when_required"})
        self.assertIsNone(g(p))
        self.assertEqual(g(p, required=True), "3.6/4.0")
        p = profile(**{"education_summary.gpa": "3.6", "education_summary.share_gpa": "never"})
        self.assertIsNone(g(p, required=True))
        self.assertTrue(any("GPA" in x for x in make_fill_js.left_for_candidate(p)))
        p = profile(**{"education_summary.gpa": "3.6/4.0", "education_summary.share_gpa": "share"})
        self.assertEqual(g(p), "3.6/4.0")

    def test_fill_script_on_a_stub_form(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node not installed")
        p = profile(**{"education_summary.gpa": "3.6", "education_summary.share_gpa": "only_when_required"})
        fields = [
            ["Email*", "text", True], ["Are you willing to undergo a background check?", "yn", True],
            ["Are you available to work weekends?", "yn", False], ["Have you previously worked at Acme?", "yn", True],
            ["Do you need any accommodations for the interview?", "text", False],
            ["Social Security Number", "text", True], ["Date of Birth", "text", True],
            ["What is your current salary?", "text", False], ["GPA*", "text", True], ["GPA", "text", False],
            ["Location preferences", "text", False], ["Gender", "combo", False],
            ["Have you ever been convicted of a felony?", "yn", True],
        ]
        harness = """
class Input { constructor(){ this.tagName = 'INPUT'; this._v = ''; } get value(){ return this._v; } set value(v){ this._v = v; } dispatchEvent(){} }
globalThis.HTMLInputElement = Input; globalThis.HTMLTextAreaElement = Input; globalThis.Event = class {};
const FIELDS = %s;
const entries = FIELDS.map(([label, kind, req]) => {
  const f = { label, kind, input: new Input(), clicked: null };
  const btn = t => ({ innerText: t, click(){ f.clicked = t; } });
  f.querySelector = sel => sel === 'label' ? { innerText: label } : sel === 'input[type=file]' ? null
    : sel.startsWith('[required]') ? (req ? {} : null) : sel === '[role=combobox]' ? (kind === 'combo' ? {} : null) : null;
  f.querySelectorAll = sel => sel.startsWith('input:not') ? (kind === 'text' ? [f.input] : [])
    : sel.startsWith('button') ? (kind === 'yn' ? [btn('Yes'), btn('No')] : [])
    : sel.startsWith('label') ? [{ innerText: label }, { innerText: 'Female' }, { innerText: 'Male' }] : [];
  f.innerText = label; return f;
});
globalThis.document = { title: 'Apply', body: { innerText: 'Remote role' },
  querySelectorAll: s => s === '.ashby-application-form-field-entry' ? entries : [] };
const out = eval(%s);
console.log(JSON.stringify({ out, vals: entries.map(e => [e.label, e.input.value, e.clicked]) }));
""" % (json.dumps(fields), json.dumps(make_fill_js.render(p)))
        with tempfile.TemporaryDirectory() as d:
            h = os.path.join(d, "h.js")
            with open(h, "w") as fh:
                fh.write(harness)
            r = subprocess.run([node, h], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        res = json.loads(r.stdout)
        vals = {lab: (v, c) for lab, v, c in res["vals"]}
        rep = res["out"]
        self.assertEqual(vals["Email*"][0], "jane.doe@example.com")
        self.assertEqual(vals["Are you willing to undergo a background check?"][1], "Yes")
        self.assertEqual(vals["Are you available to work weekends?"][1], "No")
        self.assertEqual(vals["Have you previously worked at Acme?"][1], "No")
        self.assertIn("(verify per company)", rep)
        self.assertEqual(vals["Do you need any accommodations for the interview?"][0], "")
        for lab in ("Social Security Number", "Date of Birth"):
            self.assertEqual(vals[lab][0], "")
            self.assertIn("LEAVE (candidate only): " + lab, rep)
        self.assertIsNone(vals["Have you ever been convicted of a felony?"][1])
        self.assertEqual(vals["What is your current salary?"][0], "Prefer not to say")
        self.assertEqual(vals["GPA*"][0], "3.6/4.0")
        self.assertEqual(vals["GPA"][0], "")
        self.assertEqual(vals["Location preferences"][0], "")
        self.assertIn("hint: Decline to self-identify", rep)


class Sources(unittest.TestCase):
    def test_plan_from_profile(self):
        rows = sources.plan(profile(), "Product Engineer")
        ids = [r["id"] for r in rows]
        self.assertNotIn("handshake", ids)                               # not in the fixture's search.sources
        self.assertEqual(ids[:2], ["linkedin", "indeed"])
        by = {r["name"]: r for r in rows}
        self.assertTrue(by["Wellfound"]["login_required"])
        self.assertTrue(by["LinkedIn"]["login_required"])
        self.assertFalse(by["Indeed"]["login_required"])
        self.assertEqual(by["Ashby boards"]["source_label"], "Ashby — official company careers")
        extra = by["Austin Tech Jobs"]
        self.assertEqual(extra["search_url"], "https://jobs.example.org/search?q=Product+Engineer")
        self.assertEqual(extra["source_label"], "Austin Tech Jobs")
        self.assertEqual(extra["playbook"], "Extra portals")
        self.assertFalse(extra["login_required"])

    def test_handshake_unknown_and_base_url(self):
        p = profile(**{"search.sources": ["handshake", "dice", "monster"], "targets.employment_types": ["full_time"],
                       "search.extra_portals": [{"name": "Guild Board", "url": "https://guild.example.org",
                                                  "login_required": True}]})
        rows = sources.plan(p, "Analyst")
        hs, dice, unknown, extra = rows
        self.assertEqual((hs["source_label"], hs["login_required"], hs["playbook"]), ("Handshake", True, "Handshake"))
        self.assertIn("search-contract-jobs", dice["note"])             # no contract type picked
        self.assertEqual(sources.plan(profile(**{"search.sources": ["dice"]}))[0]["note"], "")  # fixture picks C2C
        self.assertFalse(unknown["known"])
        self.assertEqual(extra["search_url"], "https://guild.example.org")
        self.assertTrue(extra["login_required"])

    def test_every_playbook_heading_exists(self):
        with open(os.path.join(ROOT, ".claude", "skills", "search-jobs", "references", "search-workflow.md")) as fh:
            doc = fh.read()
        heads = [l[4:] for l in doc.splitlines() if l.startswith("### ")]
        for sid in config.KNOWN_SOURCES:
            pb = sources.PLAYBOOK[sid]
            self.assertTrue(any(h.startswith(pb) for h in heads), pb)
            self.assertIn(sid, sources.SOURCE_LABEL)
        self.assertTrue(any(h.startswith("Extra portals") for h in heads))


PAGE = """<table><tr><th>EMPLOYER</th></tr>
<tr><td>ACME INC</td><td>SOFTWARE ENGINEER</td><td>150,000</td><td>AUSTIN, TX</td><td>01/10/{y}</td><td>02/01/{y}</td><td>CERTIFIED</td></tr>
<tr><td>ACME INC</td><td>SOFTWARE ENGINEER</td><td>190,000</td><td>AUSTIN, TX</td><td>03/10/{y}</td><td>04/01/{y}</td><td>CERTIFIED</td></tr>
<tr><td>ACME HOLDINGS</td><td>DATA ENGINEER</td><td>160,000</td><td>AUSTIN, TX</td><td>05/10/2015</td><td>06/01/2015</td><td>CERTIFIED</td></tr>
</table>"""


class H1bModule(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.env = mock.patch.dict(os.environ, {"H1B_CACHE": os.path.join(self.d, "cache.json")})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.d)

    def test_parse_and_lookup(self):
        page = PAGE.format(y=h1b_lookup.RECENT_FROM)
        rows = h1b_lookup._parse(page)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["wage"], 150000)
        with mock.patch.object(h1b_lookup, "_fetch", lambda q: page) as _:
            r = h1b_lookup.lookup("Acme")
        self.assertEqual(r["verdict"], "some")
        self.assertEqual(r["count_recent"], 2)
        self.assertEqual(r["count_all"], 3)
        self.assertEqual(r["median_wage"], 170000)
        self.assertTrue(h1b_lookup.evidence(r).startswith(f"some: 2 filings since {h1b_lookup.RECENT_FROM}, median $170,000"))
        with mock.patch.object(h1b_lookup, "_fetch", side_effect=AssertionError("cache should be used")):
            self.assertEqual(h1b_lookup.lookup("Acme")["verdict"], "some")

    def test_ambiguous_and_none(self):
        page = "".join(f"<tr><td>TITAN {w}</td><td>X</td><td>1</td><td>Y</td><td>01/01/2025</td><td>Z</td></tr>"
                       for w in ("STEEL WORKS", "FOODS", "PAINTS"))
        with mock.patch.object(h1b_lookup, "_fetch", lambda q: page):
            r = h1b_lookup.lookup("Titan", force=True)
        self.assertEqual(r["verdict"], "unknown")
        self.assertEqual(h1b_lookup.evidence(r), "lookup ambiguous: check the employer name by hand")
        with mock.patch.object(h1b_lookup, "_fetch", lambda q: "<html></html>"):
            r = h1b_lookup.lookup("Nobody Startup", force=True)
        self.assertEqual(r["verdict"], "none")
        self.assertIn("no LCA filings", h1b_lookup.evidence(r))

    def test_failed_lookup(self):
        def boom(q):
            raise OSError("offline")
        with mock.patch.object(h1b_lookup, "_fetch", boom):
            r = h1b_lookup.lookup("Acme", force=True)
        self.assertEqual(r["verdict"], "unknown")
        self.assertEqual(h1b_lookup.evidence(r), "lookup failed")


class CompanyList(unittest.TestCase):
    def test_parse_list(self):
        got = company_list.parse_list(["- Acme: https://acme.example/careers", "Globex - globex.io", "Initech", ""])
        self.assertEqual(got, [("Acme", "https://acme.example/careers"), ("Globex", "globex.io"), ("Initech", "")])

    def test_loc_fit_and_titles(self):
        p = profile()
        self.assertEqual(company_list.loc_fit("Austin, TX", False, p), "Target area")
        self.assertEqual(company_list.loc_fit("Remote", True, p), "Remote US")
        self.assertEqual(company_list.loc_fit("London", False, p), "non-US")
        self.assertEqual(company_list.loc_fit("Seattle, WA", False, p), "US other")
        self.assertEqual(company_list.loc_fit("Seattle, WA", False, profile(**{"locations.relocation_anywhere_us": True})), "Target area")
        self.assertTrue(company_list.title_ok("Senior Full Stack Engineer", p))
        self.assertFalse(company_list.title_ok("Staff Product Engineer", p))


class Cli(unittest.TestCase):
    def test_scripts_show_help(self):
        env = {**os.environ, "JOB_KIT_PROFILE": FIXTURE}
        for s in (os.path.join(ROOT, "scripts", "screen.py"), os.path.join(SJ, "check_dupes.py"),
                  os.path.join(SJ, "company_list.py"), os.path.join(AB, "fetch_ats.py"), os.path.join(AB, "filter_jobs.py"),
                  os.path.join(AB, "build_rows.py"), os.path.join(AB, "gate.py"), os.path.join(AB, "make_fill_js.py"),
                  os.path.join(SJ, "sources.py"), os.path.join(H1B, "h1b_lookup.py")):
            r = subprocess.run([sys.executable, s, "--help"], capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0, s + r.stderr)

    def test_gate_cli_h1b_off(self):
        with tempfile.TemporaryDirectory() as d:
            kept = os.path.join(d, "kept.json")
            json.dump([{"co": "Acme", "title": "Senior Software Engineer", "desc": TS_DESC, "loc": "Austin, TX", "comp": ""}], open(kept, "w"))
            r = subprocess.run([sys.executable, os.path.join(AB, "gate.py"), "--kept", kept, "--h1b"], capture_output=True, text=True,
                               env={**os.environ, "JOB_KIT_PROFILE": FIXTURE})
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("modules.h1b is off", r.stdout)
            self.assertEqual(json.load(open(os.path.join(d, "gated.json")))[0]["verdict"], "PASS")

    def test_missing_profile_stops_with_setup_hint(self):
        r = subprocess.run([sys.executable, os.path.join(AB, "gate.py"), "--kept", "x.json"], capture_output=True, text=True,
                           env={**os.environ, "JOB_KIT_PROFILE": os.path.join(tempfile.gettempdir(), "no-such-profile.json")})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("setup.sh", r.stderr)


if __name__ == "__main__":
    unittest.main()

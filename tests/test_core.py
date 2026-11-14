"""Core: config loader, doctor, and setup.sh (run in a throwaway copy of the repo)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "profile.json")
sys.path.insert(0, ROOT)
os.environ["JOB_KIT_PROFILE"] = FIXTURE
from core import config  # noqa: E402


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.p = config.load()

    def test_fixture_is_valid(self):
        errors, warns = config.validate(self.p)
        self.assertEqual(errors, [])

    def test_example_keys_are_merged_into_partial_profile(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"identity": {"full_name": "Sam Lee"}}, f)
        try:
            os.environ["JOB_KIT_PROFILE"] = f.name
            p = config.load()
            self.assertEqual(config.full_name(p), "Sam Lee")
            self.assertEqual(config.get(p, "followups.quiet_days"), 10)  # from the example
            self.assertEqual(config.get(p, "identity.country"), "United States")
        finally:
            os.environ["JOB_KIT_PROFILE"] = FIXTURE
            os.unlink(f.name)

    def test_helpers(self):
        self.assertEqual(config.first_name(self.p), "Jane")
        self.assertEqual(config.file_stem(self.p), "Jane_Doe")
        self.assertTrue(config.sheet_url(self.p, 7).endswith("#gid=0&range=A7"))
        self.assertEqual(config.pay_floor(self.p), 150000)
        self.assertFalse(config.module_on(self.p, "h1b"))

    def test_location_regex(self):
        loc = config.loc_regex(self.p)
        for ok in ("Austin, TX", "Remote - United States", "Dallas"):
            self.assertRegex(ok, loc)
        self.assertIsNone(loc.search("Seattle, WA"))
        p = dict(self.p, locations=dict(self.p["locations"], relocation_anywhere_us=True))
        self.assertRegex("Seattle, WA", config.loc_regex(p))
        self.assertRegex("London, UK", config.non_us_regex())

    def test_validate_catches_problems(self):
        bad = json.loads(json.dumps(self.p))
        bad["identity"]["full_name"] = ""
        bad["targets"]["title_include_regex"] = "(unclosed"
        bad["resumes"][0]["path"] = "resumes/base/nope.pdf"
        bad["pay"]["position_in_posted_range"] = 3
        errors, _ = config.validate(bad)
        joined = " ".join(errors)
        for frag in ("identity.full_name", "title_include_regex", "nope.pdf", "position_in_posted_range"):
            self.assertIn(frag, joined)

    def test_employment_types(self):
        self.assertEqual(config.employment_types(self.p), ["full_time", "contract_c2c"])
        self.assertTrue(config.wants_contract(self.p))
        self.assertTrue(config.module_on(self.p, "c2c"))
        self.assertEqual(config.employment_label("contract_c2c"), "Contract (C2C)")
        self.assertEqual(config.employment_label("nope"), "Not stated")
        self.assertEqual(config.employment_type_of("Contract (C2C)"), "contract_c2c")
        self.assertEqual(config.employment_type_of("Contract"), "contract")
        ft_only = dict(self.p, targets=dict(self.p["targets"], employment_types=["full_time"]))
        self.assertFalse(config.module_on(ft_only, "c2c"))
        default = dict(self.p, targets={k: v for k, v in self.p["targets"].items() if k != "employment_types"})
        self.assertEqual(config.employment_types(default), ["full_time"])

    def test_employment_type_validation(self):
        p = json.loads(json.dumps(self.p))
        p["targets"]["employment_types"] = ["full_time", "gig"]
        errors, _ = config.validate(p)
        self.assertTrue(any("gig" in e for e in errors))
        p["targets"]["employment_types"] = ["contract_1099"]
        p["work_authorization"]["needs_sponsorship"] = True
        p["work_authorization"]["any_employer_answer"] = "No"
        p["pay"]["hourly_floor"] = 0
        _, warns = config.validate(p)
        self.assertTrue(any("1099" in w for w in warns))
        self.assertTrue(any("hourly_floor" in w for w in warns))

    def test_portals(self):
        self.assertIn("wellfound", config.sources(self.p))
        portal = config.extra_portals(self.p)[0]
        self.assertEqual(config.search_url(portal, "senior react"), "https://jobs.example.org/search?q=senior+react")
        self.assertEqual(config.search_url({"url": "https://x.example"}, "q"), "https://x.example")
        default = dict(self.p, search={k: v for k, v in self.p["search"].items() if k != "sources"})
        self.assertEqual(config.sources(default)[:3], ["linkedin", "handshake", "indeed"])
        p = json.loads(json.dumps(self.p))
        p["search"]["sources"].append("myspace")
        p["search"]["extra_portals"].append({"name": "No URL"})
        errors, warns = config.validate(p)
        self.assertTrue(any("myspace" in w for w in warns))
        self.assertTrue(any("No URL" in e for e in errors))

    def test_common_answers(self):
        self.assertEqual(config.unanswered(self.p), [])
        p = json.loads(json.dumps(self.p))
        p["screening"]["drug_test_ok"] = "ask"
        p["eeo"]["gender"] = ""
        self.assertIsNone(config.answer(p, "screening.drug_test_ok"))
        self.assertEqual(config.answer(p, "screening.age_18_plus"), "Yes")
        self.assertEqual(config.unanswered(p), ["eeo.gender"])  # "ask" is a deliberate answer
        _, warns = config.validate(p)
        self.assertTrue(any("common form question" in w for w in warns))
        for key in config.COMMON_ANSWERS:  # every common key exists in the example
            self.assertIsNot(config.get(config._example_defaults(), key, config._MISSING), config._MISSING, key)

    def test_question_bank_keys_exist(self):
        """Every config key named in the /setup question bank exists in the example profile."""
        import re as _re
        bank = _read(os.path.join(ROOT, ".claude/skills/setup/references/questions.md"))
        ex = config._example_defaults()
        keys = set(_re.findall(r"`((?:identity|current_role|education_summary|eeo|work_authorization|screening|logistics|"
                               r"locations|pay|targets|search)\.[a-z_]+)(?:\[\])?`", bank))
        self.assertGreater(len(keys), 40)
        missing = sorted(k for k in keys if config.get(ex, k, config._MISSING) is config._MISSING)
        self.assertEqual(missing, [])

    def test_sponsorship_warnings(self):
        p = json.loads(json.dumps(self.p))
        p["modules"]["h1b"] = True
        _, warns = config.validate(p)
        self.assertTrue(any("modules.h1b" in w for w in warns))

    def test_no_machine_specific_paths_in_core(self):
        for rel in ("core/config.py", "config/profile.example.json", "setup.sh", "scripts/doctor.py", "CLAUDE.md"):
            text = _read(os.path.join(ROOT, rel)).lower()
            for word in ("/users/", "/home/", "~/job-search", "~/desktop"):
                self.assertNotIn(word, text, f"{word} in {rel}")


PERSONAL_TOP_LEVEL = {"profile", "memory", "applications", "batches", "tracker", "reviews", "followups",
                      "interview-prep", "resumes", "soul.md"}


class NoPersonalDataInToolingTest(unittest.TestCase):
    """Guards contributions to the template: the real user's details must not leak into tooling files."""
    TOOLING = ("core", "scripts", ".claude", "modules", "resume", "templates", "tests", "config/profile.example.json")

    def test_real_profile_not_in_tooling(self):
        real = os.path.join(ROOT, "config", "profile.json")
        if not os.path.exists(real):
            self.skipTest("no config/profile.json (template checkout)")
        p = json.loads(_read(real))
        ident = p.get("identity", {})
        needles = [v.lower() for v in (ident.get("full_name"), ident.get("email"), ident.get("phone"),
                                       config.get(p, "tracker.sheet_id")) if v and len(v) > 4]
        hits = []
        for top in self.TOOLING:
            base = os.path.join(ROOT, top)
            files = [base] if os.path.isfile(base) else [
                os.path.join(d, f) for d, _, fs in os.walk(base) if "__pycache__" not in d for f in fs]
            for fp in files:
                try:
                    text = _read(fp, encoding="utf-8").lower()
                except (UnicodeDecodeError, OSError):
                    continue
                hits += [f"{os.path.relpath(fp, ROOT)}: {n}" for n in needles if n in text]
        self.assertEqual(hits, [])


def _copy_repo(dst):
    """Copy the kit without anyone's personal data (only top-level data folders are skipped)."""
    def ignore(d, names):
        skip = {n for n in names if n in (".git", ".venv", "__pycache__")}
        if os.path.abspath(d) == ROOT:
            skip |= PERSONAL_TOP_LEVEL & set(names)
        if os.path.abspath(d) == os.path.join(ROOT, "config"):
            skip |= {"profile.json"} & set(names)
        return skip
    shutil.copytree(ROOT, dst, ignore=ignore)


class SetupScriptTest(unittest.TestCase):
    def test_setup_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = os.path.join(tmp, "kit")
            _copy_repo(repo)
            env = {k: v for k, v in os.environ.items() if k != "JOB_KIT_PROFILE"}
            run = lambda: subprocess.run(["bash", "setup.sh", "--no-venv"], cwd=repo, env=env,  # noqa: E731
                                         capture_output=True, text=True, timeout=120)
            r1 = run()
            self.assertEqual(r1.returncode, 0, r1.stdout + r1.stderr)
            for f in ("profile/answer_bank.md", "profile/master_cv.md", "profile/stories.md", "soul.md",
                      "memory/MEMORY.md", "applications/_events.jsonl", "resumes/base/.gitkeep"):
                self.assertTrue(os.path.exists(os.path.join(repo, f)), f)
            self.assertTrue(os.path.isdir(os.path.join(repo, ".git")))
            self.assertIn("/setup", r1.stdout)

            edited = os.path.join(repo, "soul.md")
            with open(edited, "w") as fh:
                fh.write("my edits\n")
            r2 = run()
            self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
            self.assertEqual(_read(edited), "my edits\n")
            self.assertIn("kept    soul.md", r2.stdout)


class DoctorTest(unittest.TestCase):
    def test_doctor_json_reports_profile_ok(self):
        r = subprocess.run([sys.executable, "scripts/doctor.py", "--json", "--offline"], cwd=ROOT,
                           capture_output=True, text=True, env=dict(os.environ, JOB_KIT_PROFILE=FIXTURE))
        data = json.loads(r.stdout)
        profile = [i for i in data["items"] if i["area"] == "profile"]
        self.assertTrue(any(i["level"] == "ok" and "Jane Doe" in i["msg"] for i in profile), profile)

    def test_doctor_fails_without_profile(self):
        r = subprocess.run([sys.executable, "scripts/doctor.py", "--json", "--offline"], cwd=ROOT,
                           capture_output=True, text=True,
                           env=dict(os.environ, JOB_KIT_PROFILE="/nonexistent/profile.json"))
        data = json.loads(r.stdout)
        self.assertTrue(data["failed"])
        self.assertEqual(r.returncode, 1)


if __name__ == "__main__":
    unittest.main()

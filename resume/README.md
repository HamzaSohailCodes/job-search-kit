# Resume engine

Renders the candidate's resume from data, `profile/resume_content.json`, as HTML, LaTeX/PDF (Tectonic) and DOCX
in one design, and checks the PDF the way an applicant tracking system will read it. `/setup` writes the content
file from the candidate's resume; `/build-batch-resume` tailors it per job. No resume content lives in code.

| File | What |
|---|---|
| `engine.py` | Loads and normalises the content; resolves a version into what is printed; HTML and DOCX renderers; headless-Chrome PDF fallback. |
| `latex.py` | LaTeX renderer and `build_fit()` (tightens spacing until the PDF fits `resume_build.pages`). |
| `build.py` | CLI: builds every base version into `resumes/base/`. |
| `cover.py` | One-page cover letter in the same design, from a small JSON file Claude writes. |
| `template.css` | The HTML design (also the reference for the LaTeX and DOCX colours and spacing). |
| `verify_pdf.py`, `verify_layout.py` | Ported from ai-job-search (MIT, see `THIRD_PARTY_NOTICES.md`): exact page count, ASCII date ranges, literal contact text; holes, orphaned job titles, thin last page. |
| `pdf_pages.js` | macOS only: renders PDF pages to PNG and prints the text layer (`osascript -l JavaScript resume/pdf_pages.js <pdf> <outdir>`). |

## Build

```bash
./setup.sh                                   # once: .venv with pypdf + python-docx
brew install tectonic poppler                # optional system tools: PDF build and the layout check
.venv/bin/python resume/build.py             # all versions -> resumes/base/<First_Last>_Resume_<Version>.{html,tex,pdf,docx}
.venv/bin/python resume/build.py --version Backend --formats html,pdf
.venv/bin/python resume/build.py --content templates/profile/resume_content.example.json --out /tmp/demo   # the fake example
.venv/bin/python resume/verify_pdf.py resumes/base/Jane_Doe_Resume_FullStack.pdf --pages 2 --ascii-dates --contains jane.doe@example.com
.venv/bin/python resume/verify_layout.py --footer-band 0 resumes/base/Jane_Doe_Resume_FullStack.pdf
```
Without Tectonic, `--engine chrome` prints the HTML with headless Chrome (or set `resume_build.engine`).
Without python-docx the DOCX is skipped with a note.

Settings (all optional, read from `config/profile.json` under `resume_build`): `pages` (2), `exact_pages` (true:
the checks want exactly that many pages), `engine` ("latex"), `font` ("Arial"; falls back to Liberation Sans or
Tectonic's TeX Gyre Heros), `content_path` ("profile/resume_content.json"), `chrome_path`, `tailoring_mode`
("70/30" or "full"), `batch_size`, `batch_days`, `min_score`. Tests point `$JOB_KIT_RESUME_CONTENT` at a fixture.

## resume_content.json schema

A full fake example: `templates/profile/resume_content.example.json`. Text fields accept a small inline-HTML
subset: `<b>`, `<i>`, `<a href="...">`, `<br>`; `&` may be written plain. Everything here must also be in
`profile/master_cv.md`.

```text
schema_version   1
header           {name, contact_lines: [str, ...]}         optional; built from config identity.* when omitted
section_titles   {summary, skills, certifications, experience, projects, education}   optional headings
section_order    ["summary","skills","certifications","experience","projects","education","extras"]
skills           [{id, label, category, items: [str]}]       category: languages|frontend|backend|data|cloud|
                                                             testing|architecture|ai|leadership; inventory tools
                                                             join the line with their category
certifications   [{title, when, meta}]
jobs             [{id, employer, url, employer_note, title, location, dates, context, stack, domains: [str],
                   optional: bool, bullets: [{id, text}]}]   dates like "Mar 2021 – Present" (printed ASCII in PDF)
projects         [{id, title, bullets: [str]}]
education        [{degree, school}]
extra_sections   [{title, entries: [{title, when, style: "bullets"|"pub", bullets: [str]}]}]
default_version  name of a version
versions         {Name: {headline, headline_base, summary, skills: [skills ids], jobs: {job id: [bullet ids]},
                   projects_title, projects: [project ids], match: [keyword terms], title_regex, title_boost}}
keyword_aliases  {term: regex}   extra or corrected posting patterns for the tailoring matcher
```

- A **version** is one base resume (for example FullStack, Backend, AI_Engineer): it picks the headline, the
  summary, the skill-line order and which bullets appear in which order. Facts are shared; only selection and
  order differ. `match` and `title_regex` tell the tailoring script which version a posting is closest to.
- Bullet **ids** are stable handles: tailoring, reviewer edits (`reorder`, `swap`) and master_cv.md all refer to them.
- `domains` per job name the areas where the candidate has real exposure; the tailoring skill uses them to choose
  an honest domain bridge for a summary's first sentence.

## How tailoring keeps ~70% fixed and tunes ~30%

`/build-batch-resume` (`.claude/skills/build-batch-resume/scripts/tailor_batch.py`) never writes new facts:
- **Fixed (~70%)**: every bullet's wording, every base skill term, employers, titles, dates, metrics, education,
  certifications, and the summary body.
- **Tuned (~30%)**: the base version picked for the posting; the order of skill lines, terms, bullets and
  projects; a headline from the posting's title plus its top matched tools; the posting's spelling (ReactJS,
  Postgres) and acronyms spelled out once; a short "Hands-on with ..." summary closer for must-haves that would
  appear only once; up to 4 tools from `profile/skills_inventory.md`'s "Used" table that the posting names; and
  Claude's one-sentence summary lead in the company's domain language.
- Each resume reports its **core share** (words shared with the untailored version; below 70% is flagged),
  keyword counts, a requirement → evidence-bullet map, gaps (asked for, never added), and the PDF checks.

The optional full mode (`resume_build.tailoring_mode: "full"`) rewrites each resume from `profile/master_cv.md`
via a per-job `custom.json`, guarded by `build_custom.py` (no unconfirmed numbers, no never-claim tools, no
dropped jobs, project titles unchanged). See the skill's `references/custom_cv.md`.

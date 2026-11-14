#!/usr/bin/env python3
"""Build the base resume versions from profile/resume_content.json.

Writes resumes/base/<First_Last>_Resume_<Version>.{html,tex,pdf,docx} for every version in the content file
(or only --version X). The PDF comes from LaTeX via Tectonic, fitted to `resume_build.pages` (default 2);
--engine chrome prints the HTML with headless Chrome instead. DOCX needs python-docx (in .venv).

Usage (from the repo root):
  .venv/bin/python resume/build.py                       # all versions
  .venv/bin/python resume/build.py --version FullStack --formats html,pdf
  .venv/bin/python resume/build.py --content templates/profile/resume_content.example.json --out /tmp/x
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from resume import engine, latex  # noqa: E402
from core import config  # noqa: E402


def build_one(R, v, base, formats, engine_name="latex", title=None, keywords="", pages=None):
    """Write the requested formats for one version. Returns a dict of what was written and the fit result."""
    res = {"base": base}
    if "html" in formats or engine_name == "chrome":
        with open(base + ".html", "w", encoding="utf-8") as f:
            f.write(engine.html_version(R, v))
        res["html"] = base + ".html"
    if "pdf" in formats or "tex" in formats:
        if engine_name == "latex" and latex.have_tectonic():
            res["pages"], res["spacing_level"] = latex.build_fit(R, v, base, title, keywords, pages)
            res["pdf"], res["tex"] = base + ".pdf", base + ".tex"
        elif engine_name == "latex" and "pdf" not in formats:
            with open(base + ".tex", "w", encoding="utf-8") as f:
                f.write(latex.tex_version(R, v, title, keywords))
            res["tex"] = base + ".tex"
        else:
            if engine_name == "latex":
                print("tectonic not found: falling back to headless Chrome for the PDF", file=sys.stderr)
                with open(base + ".html", "w", encoding="utf-8") as f:
                    f.write(engine.html_version(R, v))
            engine.to_pdf(base + ".html", base + ".pdf")
            res["pdf"], res["pages"] = base + ".pdf", latex.pdf_pages(base + ".pdf")
    if "docx" in formats:
        if engine.have_docx():
            engine.docx_version(R, v, base + ".docx")
            res["docx"] = base + ".docx"
        else:
            print("python-docx not installed: skipped DOCX (run ./setup.sh)", file=sys.stderr)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--content", help="resume content JSON (default: profile/resume_content.json)")
    ap.add_argument("--version", help="one version name (default: all)")
    ap.add_argument("--out", default=config.path("resumes", "base"))
    ap.add_argument("--formats", default="html,pdf,docx")
    ap.add_argument("--engine", default=None, choices=["latex", "chrome"])
    a = ap.parse_args()
    p = engine.profile()
    R = engine.load_content(a.content, p)
    eng = a.engine or engine.setting("engine", "latex", p)
    formats = set(a.formats.split(","))
    pages = int(engine.setting("pages", 2, p))
    os.makedirs(a.out, exist_ok=True)
    stem = engine.file_stem(p) if p else R["name"].replace(" ", "_")
    for name in ([a.version] if a.version else list(R["versions"])):
        v = engine.version(R, name)
        base = os.path.join(a.out, f"{stem}_Resume_{name}")
        r = build_one(R, v, base, formats, eng, f"{R['name']} - {name.replace('_', ' ')} Resume", pages=pages)
        n = r.get("pages")
        msg = f"  pages {n}, spacing level {r.get('spacing_level', '-')}" if n else ""
        if n and n > pages:
            msg += f"  << over {pages} pages: cut content"
        print(f"built {base}.{{{','.join(k for k in ('html', 'tex', 'pdf', 'docx') if k in r)}}}{msg}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""One-page cover letter in the resume's design (LaTeX via Tectonic). Used only when a form asks for one.

Claude writes the text; this file only lays it out. Input is a small JSON file:
  {"company": "Acme", "role": "Senior Software Engineer", "greeting": "Dear Hiring Team,",
   "paragraphs": ["...", "..."], "closing": "Best regards,", "date": "November 4, 2026"}
Rules for the text (soul.md and ai-job-search's cover letter guide): first person, plain text, no dashes,
about 250 to 350 words, every claim already on the resume, the posting's own words for its must-haves,
one honest line for a real gap if it matters, a different story from the resume's top bullet where possible.

Usage: .venv/bin/python resume/cover.py letter.json --out DIR
Writes DIR/<First_Last>_Cover_Letter.{tex,pdf}; check it with resume/verify_pdf.py --pages 1.
"""
import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from resume import engine  # noqa: E402
from resume.latex import esc, font_spec, tex, tex_to_pdf  # noqa: E402

TEMPLATE = r"""\documentclass[11pt]{article}
\usepackage[letterpaper,top=0.6in,bottom=0.6in,left=0.85in,right=0.85in]{geometry}
\usepackage{fontspec}
%(fontspec)s
\usepackage{xcolor}
\definecolor{navy}{HTML}{153B54}\definecolor{blue}{HTML}{176F9C}\definecolor{rule}{HTML}{168FC6}
\definecolor{grey}{HTML}{415D70}\definecolor{ink}{HTML}{1D2B38}
\usepackage[hidelinks]{hyperref}
\hypersetup{pdftitle={%(title)s},pdfauthor={%(author)s},pdfsubject={Cover letter},pdfcreator={job-search-kit resume/cover.py},pdfproducer={Tectonic}}
\pagestyle{empty}\setlength{\parindent}{0pt}\setlength{\parskip}{9pt}\renewcommand{\baselinestretch}{1.12}\frenchspacing\raggedright\hyphenpenalty=10000\exhyphenpenalty=10000
\color{ink}
\begin{document}
{\color{rule}\hrule height 1.5pt}\vspace{6pt}
\begin{center}{\fontsize{21}{22}\selectfont\bfseries\color{navy}%(name)s}\par\vspace{4pt}
{\fontsize{8.5}{11}\selectfont\color{grey}%(contact)s}\end{center}
\vspace{4pt}
%(date)s

{\bfseries %(company)s}\\%(role_line)s

%(greeting)s

%(body)s

%(closing)s\\[2pt]
{\bfseries %(name)s}
\end{document}
"""


def cover_tex(d, R):
    today = dt.date.today()
    return TEMPLATE % {
        "fontspec": font_spec(), "title": esc(f"{R['name']} - Cover letter - {d['company']}"), "author": esc(R["name"]),
        "name": esc(R["name"]), "contact": r"\\".join(tex(c) for c in R["contact"]),
        "date": esc(d.get("date") or f"{today:%B} {today.day}, {today.year}"),
        "company": esc(d["company"]), "role_line": "Re: " + esc(d["role"]),
        "greeting": esc(d.get("greeting") or "Dear Hiring Team,"),
        "body": "\n\n".join(esc(p.strip()) for p in d["paragraphs"]),
        "closing": esc(d.get("closing") or "Best regards,"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("letter")
    ap.add_argument("--out", required=True)
    ap.add_argument("--content", help="resume content JSON (default: profile/resume_content.json)")
    a = ap.parse_args()
    p = engine.profile()
    R = engine.load_content(a.content, p)
    with open(a.letter, encoding="utf-8") as f:
        d = json.load(f)
    os.makedirs(a.out, exist_ok=True)
    base = os.path.join(a.out, f"{engine.file_stem(p)}_Cover_Letter")
    with open(base + ".tex", "w", encoding="utf-8") as f:
        f.write(cover_tex(d, R))
    print(tex_to_pdf(base + ".tex"))


if __name__ == "__main__":
    main()

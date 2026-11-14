"""Render the resume as LaTeX (XeTeX via Tectonic) in the same design as the HTML version.

Same data (R, v) as engine.html_version, same look (Arial, the template colours, centred name and headline,
blue section rules, right-aligned dates). What LaTeX adds, borrowed from ai-job-search's CV workflow:
  * \\needspace before every entry and section, so a job title never sits alone at the bottom of a page;
  * ASCII date ranges ("Sep 2025 - Present"): a Workday import was seen dropping dates joined by an en dash;
  * no hyphenation and no kerning, so every keyword extracts as one word (kerning made pypdf split words);
  * the email and phone as literal text, a single column, and PDF metadata set (ATS and Poppler friendly);
  * a .tex source that verify_pdf.py / verify_layout.py can check and Claude can fix line by line.

Needs `tectonic` (macOS: brew install tectonic). Font: config `resume_build.font` (default Arial). Arial is read
from macOS's Supplemental fonts or Liberation Sans on Linux; otherwise TeX Gyre Heros from Tectonic's bundle.
"""
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from resume import engine  # noqa: E402

FONT_DIRS = {  # name -> (dir, upright, bold, italic, bold italic)
    "mac_arial": ("/System/Library/Fonts/Supplemental/", "Arial", "Arial Bold", "Arial Italic", "Arial Bold Italic"),
    "liberation": ("/usr/share/fonts/truetype/liberation/", "LiberationSans-Regular", "LiberationSans-Bold",
                   "LiberationSans-Italic", "LiberationSans-BoldItalic"),
}


def font_spec(font=None):
    r"""The \setmainfont line. Kerning is always off (see module docstring)."""
    font = font or engine.setting("font", "Arial")
    if font.lower() == "arial":
        for d, up, b, i, bi in FONT_DIRS.values():
            if os.path.exists(os.path.join(d, up + ".ttf")):
                return (r"\setmainfont{%s}[Path=%s, Extension=.ttf, UprightFont=%s, BoldFont=%s, ItalicFont=%s, "
                        r"BoldItalicFont=%s, Kerning=Off]" % (up, d, up, b, i, bi))
        font = "texgyreheros"
    if font == "texgyreheros":  # ships with Tectonic's bundle, a Helvetica-like sans
        return (r"\setmainfont{texgyreheros}[Extension=.otf, UprightFont=*-regular, BoldFont=*-bold, "
                r"ItalicFont=*-italic, BoldItalicFont=*-bolditalic, Kerning=Off]")
    return r"\setmainfont{%s}[Kerning=Off]" % font


PREAMBLE = r"""\documentclass[10pt]{article}
\usepackage[letterpaper,top=0.42in,bottom=0.42in,left=0.5in,right=0.5in]{geometry}
\usepackage{fontspec}
%(fontspec)s
\usepackage[dvipsnames]{xcolor}
\definecolor{navy}{HTML}{153B54}\definecolor{blue}{HTML}{176F9C}\definecolor{rule}{HTML}{168FC6}
\definecolor{grey}{HTML}{415D70}\definecolor{ink}{HTML}{1D2B38}\definecolor{soft}{HTML}{6EA9C6}\definecolor{sum}{HTML}{253B4A}
\usepackage{enumitem}
\usepackage{needspace}
\usepackage[hidelinks]{hyperref}
\hypersetup{pdftitle={%(title)s},pdfauthor={%(author)s},pdfsubject={Resume},pdfkeywords={%(keywords)s},pdfcreator={job-search-kit resume/latex.py},pdfproducer={Tectonic}}
\pagestyle{empty}
\setlength{\parindent}{0pt}\setlength{\parskip}{0pt}
\renewcommand{\baselinestretch}{%(stretch)s}
\frenchspacing\raggedright\hyphenpenalty=10000\exhyphenpenalty=10000
\color{ink}
\setlist[itemize]{leftmargin=11pt,labelsep=5pt,itemsep=%(itemsep)spt,parsep=0pt,topsep=2pt,partopsep=0pt,label={\textbullet}}
\newcommand{\sect}[1]{\needspace{5\baselineskip}\vspace{%(sectgap)spt}{\fontsize{10.8}{13}\selectfont\bfseries\color{blue}\MakeUppercase{#1}}\par\vspace{1.5pt}{\color{soft}\hrule height 0.6pt}\vspace{4pt}}
\newcommand{\jobline}[2]{{\color{blue}\bfseries #1}\hfill{\fontsize{8.5}{10}\selectfont\bfseries\color{grey}#2}\par}
\newcommand{\meta}[1]{{\fontsize{8.5}{10.5}\selectfont\color{grey}#1}\par}
\begin{document}
"""


def esc(s):
    """Plain text -> LaTeX. Straight double quotes become curly pairs (XeTeX renders a bare " as a closing quote)."""
    s = re.sub(r'"([^"]*)"', "\u201c\\1\u201d", s)
    rep = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
           "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    return "".join(rep.get(ch, ch) for ch in s)


TAG = re.compile(r"<(/?)(b|i|br|a)\b([^>]*)>", re.I)


def tex(s):
    """Inline HTML (<b>, <i>, <a href>, <br>, entities) -> LaTeX, with ASCII date ranges."""
    s = ascii_dates(s or "")
    out, pos, stack = [], 0, []
    for m in TAG.finditer(s):
        out.append(esc(html.unescape(s[pos:m.start()])))
        pos = m.end()
        close, name, attrs = m.group(1), m.group(2).lower(), m.group(3)
        if name == "br":
            out.append(r"\\ ")
            continue
        if close:
            if stack:
                stack.pop()
                out.append("}")
            continue
        if name == "b":
            out.append(r"\textbf{"); stack.append("b")
        elif name == "i":
            out.append(r"\textit{"); stack.append("i")
        elif name == "a":
            href = re.search(r'href="([^"]+)"', attrs)
            url = html.unescape(href.group(1)) if href else ""
            out.append(r"\href{" + url.replace("%", r"\%").replace("#", r"\#") + "}{"); stack.append("a")
    out.append(esc(html.unescape(s[pos:])))
    out.extend("}" for _ in stack)
    return "".join(out)


def ascii_dates(s):
    """'Sep 2025 – Present' -> 'Sep 2025 - Present' (keeps other en dashes, e.g. 'Developer – Associate')."""
    return re.sub(r"(\b(?:19|20)\d{2}|Present)\s*[\u2013\u2014]\s*(?=[A-Z]?[a-z]{0,8}\.?\s*(?:19|20)\d{2}|Present)",
                  r"\1 - ", s)


def bullets(items, bold_color="navy", style="bullets"):
    def one(x):
        t = tex(x).replace(r"\textbf{", r"\textbf{\color{" + bold_color + "}")
        return r"\item " + t + "\n"
    return "\\begin{itemize}\n" + "".join(one(x) for x in items) + "\\end{itemize}\n"


# Spacing steps tried in order until the resume fits the page budget (0 = the HTML version's spacing).
TIGHT = [dict(stretch=1.065, itemsep=1.6, sectgap=9), dict(stretch=1.05, itemsep=1.2, sectgap=8),
         dict(stretch=1.035, itemsep=0.9, sectgap=7), dict(stretch=1.02, itemsep=0.6, sectgap=6)]


def tex_version(R, v, title=None, keywords="", tight=0, font=None):
    """LaTeX source for one resume version."""
    title = title or f"{R['name']} - Resume"
    p = [PREAMBLE % dict(TIGHT[tight], fontspec=font_spec(font), title=esc(title), author=esc(R["name"]),
                         keywords=esc(keywords))]
    p.append(r"{\color{rule}\hrule height 1.5pt}\vspace{6pt}")
    p.append(r"\begin{center}{\fontsize{23}{24}\selectfont\bfseries\color{navy}" + esc(R["name"]) + r"}\par\vspace{3pt}"
             r"{\fontsize{10.2}{12.5}\selectfont\bfseries\color{blue}" + tex(v.get("headline", "")) + r"}\par\vspace{4pt}"
             r"{\fontsize{8.5}{11}\selectfont\color{grey}" + r"\\".join(tex(c) for c in R["contact"]) +
             r"}\end{center}\vspace{-6pt}")
    t = R["titles"]
    for sec in R["order"]:
        if sec == "summary" and v.get("summary"):
            p.append(r"\sect{" + tex(t["summary"]) + r"}{\color{sum}" + tex(v["summary"]) + "}\\par")
        elif sec == "skills" and engine.skill_lines(R, v):
            p.append(r"\sect{" + tex(t["skills"]) + "}")
            p += [r"{\color{blue}\bfseries " + tex(lab) + r":} " + tex(items) + r"\par\vspace{1.5pt}"
                  for lab, items in engine.skill_lines(R, v)]
        elif sec == "certifications" and R["certs"]:
            p.append(r"\sect{" + tex(t["certifications"]) + "}" + r"\vspace{3pt}".join(
                r"\jobline{" + tex(c["title"]) + "}{" + tex(c["when"]) + "}" +
                (r"\meta{" + tex(c["meta"]) + "}" if c["meta"] else "") for c in R["certs"]))
        elif sec == "experience" and engine.job_entries(R, v):
            p.append(r"\sect{" + tex(t["experience"]) + "}")
            for i, j in enumerate(engine.job_entries(R, v)):
                p.append((r"\vspace{6pt}" if i else "") + r"\needspace{5\baselineskip}\jobline{" + tex(j["co"]) +
                         " | " + tex(j["title"]) + "}{" + tex(j["when"]) + "}" +
                         (r"\meta{" + tex(j["meta"]) + "}" if j["meta"] else "") + bullets(j["bullets"]))
        elif sec == "projects" and engine.project_entries(R, v):
            p.append(r"\sect{" + tex(engine.projects_title(R, v)) + "}")
            for i, (ti, bl) in enumerate(engine.project_entries(R, v)):
                p.append((r"\vspace{5pt}" if i else "") + r"\needspace{3\baselineskip}{\color{blue}\bfseries " +
                         tex(ti) + r"}\par" + bullets(bl))
        elif sec == "education" and R["education"]:
            p.append(r"\sect{" + tex(t["education"]) + "}")
            p += [r"\needspace{2\baselineskip}{\color{blue}\bfseries " + tex(d) + r"}\par " + tex(s) + r"\par\vspace{4pt}"
                  for d, s in R["education"]]
        elif sec == "extras":
            for sx in R["extras"]:
                p.append(r"\sect{" + tex(sx["title"]) + "}")
                for i, e in enumerate(sx["entries"]):
                    head = (r"\jobline{" + tex(e["title"]) + "}{" + tex(e["when"]) + "}") if e["when"] else \
                           (r"{\color{blue}\bfseries " + tex(e["title"]) + r"}\par")
                    p.append((r"\vspace{5pt}" if i else "") + r"\needspace{3\baselineskip}" + head + bullets(e["bullets"]))
    p.append("\\end{document}\n")
    return "\n".join(p)


def have_tectonic():
    return bool(shutil.which("tectonic") or os.path.exists("/opt/homebrew/bin/tectonic"))


def tectonic():
    exe = shutil.which("tectonic") or "/opt/homebrew/bin/tectonic"
    if not os.path.exists(exe):
        raise RuntimeError("tectonic not found (macOS: brew install tectonic; Linux: see tectonic-typesetting.github.io)")
    return exe


def tex_to_pdf(tex_path, pdf_path=None):
    """Compile with Tectonic (XeTeX). Raises with the log tail on failure."""
    pdf_path = pdf_path or tex_path[:-4] + ".pdf"
    with tempfile.TemporaryDirectory() as d:
        r = subprocess.run([tectonic(), "--chatter", "minimal", "--outdir", d, tex_path],
                           capture_output=True, text=True, timeout=300)
        out = os.path.join(d, os.path.basename(tex_path)[:-4] + ".pdf")
        if r.returncode or not os.path.exists(out):
            raise RuntimeError(f"tectonic failed on {tex_path}:\n" + (r.stderr or r.stdout)[-2000:])
        shutil.move(out, pdf_path)
    return pdf_path


def pdf_pages(pdf):
    try:
        from pypdf import PdfReader
        return len(PdfReader(pdf).pages)
    except ImportError:
        out = subprocess.run(["pdfinfo", pdf], capture_output=True, text=True).stdout
        m = re.search(r"^Pages:\s+(\d+)", out, re.M)
        if not m:
            raise RuntimeError("need pypdf (pip install pypdf) or poppler's pdfinfo to count pages")
        return int(m.group(1))


def build_fit(R, v, base_path, title=None, keywords="", pages=None):
    """Write <base_path>.tex and .pdf, tightening spacing step by step until it fits `pages`.

    Returns (pages, tight_level). More pages than `pages` at the last level means content must be cut
    (relevance-weighted: drop the line least relevant to this posting first, never by section order)."""
    pages = pages or int(engine.setting("pages", 2))
    n = level = 0
    for level in range(len(TIGHT)):
        with open(base_path + ".tex", "w", encoding="utf-8") as f:
            f.write(tex_version(R, v, title, keywords, level))
        tex_to_pdf(base_path + ".tex")
        n = pdf_pages(base_path + ".pdf")
        if n <= pages:
            return n, level
    return n, level

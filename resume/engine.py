"""Resume engine core: load profile/resume_content.json and render it as HTML or DOCX.

The candidate's resume is data (profile/resume_content.json, schema in resume/README.md), never code.
`load_content()` returns a normalised dict `R`; a *version* `v` (one entry of R["versions"], or a tailored
copy) says which headline, summary, skill lines, bullets and projects to show and in what order.
The same (R, v) pair feeds html_version(), docx_version() and latex.tex_version(), so all formats match.

Content path: $JOB_KIT_RESUME_CONTENT, else config `resume_build.content_path`, else profile/resume_content.json.
Standard library only, except python-docx for DOCX (imported lazily).
"""
import copy
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

_d = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(_d, "core", "config.py")) and _d != os.path.dirname(_d):
    _d = os.path.dirname(_d)
if _d not in sys.path:
    sys.path.insert(0, _d)
from core import config  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CSS_PATH = os.path.join(HERE, "template.css")

DEFAULT_TITLES = {"summary": "Summary", "skills": "Technical Skills", "certifications": "Certifications",
                  "experience": "Professional Experience", "projects": "Selected Projects", "education": "Education"}
DEFAULT_ORDER = ["summary", "skills", "certifications", "experience", "projects", "education", "extras"]


# ---------- settings ----------

def profile():
    """The candidate's config (empty dict if there is none yet, e.g. building the example)."""
    return config.load(required=False)


def setting(key, default=None, p=None):
    return config.get(profile() if p is None else p, "resume_build." + key, default)


def content_path(p=None):
    env = os.environ.get("JOB_KIT_RESUME_CONTENT")
    if env:
        return os.path.expanduser(env)
    rel = setting("content_path", "profile/resume_content.json", p)
    return rel if os.path.isabs(rel) else config.path(rel)


def file_stem(p=None):
    return config.file_stem(profile() if p is None else p)


# ---------- loading ----------

_ENTITY = re.compile(r"&(?!(amp|lt|gt|quot|apos|nbsp|#\d+|#x[0-9a-fA-F]+);)")


def inline(s):
    """Normalise a text field to the inline-HTML subset the renderers expect: bare & becomes &amp;."""
    return _ENTITY.sub("&amp;", s or "")


def plain(s):
    """Inline HTML -> plain text."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def load_content(path=None, p=None):
    """Read resume_content.json and return the normalised dict R. Exits with a clear message if missing."""
    path = path or content_path(p)
    if not os.path.exists(path):
        sys.exit(f"No resume content at {path}. Run /setup (it writes profile/resume_content.json), "
                 "or copy templates/profile/resume_content.example.json there and edit it.")
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return normalise(raw, p, path)


def _contact_from_profile(p):
    g = lambda k: config.get(p, "identity." + k, "") or ""
    loc = ", ".join(x for x in [g("city"), g("state")] if x)
    short = lambda u: re.sub(r"^https?://(www\.)?", "", u).rstrip("/")
    l1 = " · ".join(x for x in [loc, g("phone"), g("email")] if x)
    l2 = " · ".join(short(x) for x in [g("linkedin"), g("github"), g("website")] if x)
    return [x for x in (l1, l2) if x]


def normalise(raw, p=None, path=""):
    p = profile() if p is None else p
    hd = raw.get("header", {}) or {}
    name = hd.get("name") or config.get(p, "identity.full_name", "") or "Candidate"
    contact = [inline(x) for x in (hd.get("contact_lines") or _contact_from_profile(p))]

    skills = {}
    for g in raw.get("skills", []):
        items = g.get("items", [])
        if isinstance(items, str):
            items = [x.strip() for x in re.split(r",(?![^()]*\))", items) if x.strip()]
        skills[g["id"]] = {"label": inline(g.get("label", g["id"])), "items": [inline(x) for x in items],
                           "category": g.get("category", "")}

    jobs, bullets = {}, {}
    for j in raw.get("jobs", []):
        co = html.escape(j.get("employer", ""), quote=False)
        if j.get("url"):
            co = f'<a class="co" href="{html.escape(j["url"])}">{co}</a>'
        if j.get("employer_note"):
            co += " " + inline(j["employer_note"])
        when = " | ".join(x for x in [j.get("location", ""), j.get("dates", "")] if x)
        bl = {}
        for i, b in enumerate(j.get("bullets", [])):
            bid, text = (b.get("id") or f"{j['id']}_{i + 1}", b.get("text", "")) if isinstance(b, dict) else (f"{j['id']}_{i + 1}", b)
            bl[bid] = inline(text)
        bullets.update(bl)
        jobs[j["id"]] = {"co": co, "employer": j.get("employer", ""), "title": inline(j.get("title", "")),
                         "when": inline(when), "dates": j.get("dates", ""), "context": inline(j.get("context", "")),
                         "stack": inline(j.get("stack", "")), "domains": j.get("domains", []),
                         "bullets": list(bl), "optional": bool(j.get("optional"))}

    projects = {}
    for pr in raw.get("projects", []):
        bl = [inline(b.get("text", "") if isinstance(b, dict) else b) for b in pr.get("bullets", [])]
        projects[pr["id"]] = {"title": inline(pr.get("title", "")), "bullets": bl}

    versions = {}
    for k, v in (raw.get("versions") or {}).items():
        v = copy.deepcopy(v)
        v.setdefault("skills", list(skills))
        v.setdefault("jobs", {jid: list(j["bullets"]) for jid, j in jobs.items()})
        v.setdefault("projects", list(projects))
        for f in ("headline", "summary", "projects_title", "headline_base"):
            if f in v:
                v[f] = inline(v[f])
        versions[k] = v
    if not versions:
        versions["Main"] = {"headline": config.get(p, "current_role.title", ""), "summary": "",
                            "skills": list(skills), "jobs": {jid: list(j["bullets"]) for jid, j in jobs.items()},
                            "projects": list(projects)}

    return {
        "path": path, "raw": raw, "name": name, "contact": contact,
        "titles": dict(DEFAULT_TITLES, **(raw.get("section_titles") or {})),
        "order": raw.get("section_order") or DEFAULT_ORDER,
        "skills": skills, "jobs": jobs, "bullets": bullets, "projects": projects,
        "certs": [{k: inline(c.get(k, "")) for k in ("title", "when", "meta")} for c in raw.get("certifications", [])],
        "education": [(inline(e.get("degree", "")), inline(e.get("school", ""))) for e in raw.get("education", [])],
        "extras": [{"title": inline(s.get("title", "")),
                    "entries": [{"title": inline(e.get("title", "")), "when": inline(e.get("when", "")),
                                 "style": e.get("style", "bullets"),
                                 "bullets": [inline(b) for b in e.get("bullets", [])]} for e in s.get("entries", [])]}
                   for s in raw.get("extra_sections", [])],
        "versions": versions,
        "default_version": raw.get("default_version") or next(iter(versions)),
        "aliases": raw.get("keyword_aliases") or {},
    }


def version(R, name=None):
    """A deep copy of one base version (default_version when name is None)."""
    return copy.deepcopy(R["versions"][name or R["default_version"]])


# ---------- resolving a version into what is printed ----------

def skill_lines(R, v):
    """[(label, 'a, b, c')]; entries are a skills-group id or a [label, items] pair (custom resumes)."""
    out = []
    for k in v.get("skills", []):
        if isinstance(k, str):
            if k in R["skills"]:
                g = R["skills"][k]
                out.append((g["label"], ", ".join(g["items"])))
        else:
            lab, items = k
            out.append((inline(lab), inline(items if isinstance(items, str) else ", ".join(items))))
    return out


def job_entries(R, v):
    """[{co, title, when, meta, bullets}]. v["jobs"] maps job id -> bullet ids (or literal bullet text)."""
    out = []
    for jid, bl in v.get("jobs", {}).items():
        j = R["jobs"].get(jid)
        if not j:
            continue
        stack = v.get("stack", {}).get(jid, j["stack"])
        meta = " · ".join(x for x in [j["context"], f"Stack: {inline(stack)}" if stack else ""] if x)
        out.append({"id": jid, "co": j["co"], "title": j["title"], "when": j["when"], "meta": meta,
                    "bullets": [R["bullets"].get(b, inline(b)) for b in bl]})
    return out


def project_entries(R, v):
    out = []
    for k in v.get("projects", []):
        if isinstance(k, str):
            if k in R["projects"]:
                out.append((R["projects"][k]["title"], R["projects"][k]["bullets"]))
        else:
            t, bl = k
            out.append((inline(t), [inline(b) for b in bl]))
    return out


def projects_title(R, v):
    return v.get("projects_title") or R["titles"]["projects"]


def resume_text(R, v):
    """Plain text of everything a version prints (for keyword counts and core share)."""
    parts = [R["name"], v.get("headline", ""), v.get("summary", "")]
    parts += [f"{a}: {b}" for a, b in skill_lines(R, v)]
    for c in R["certs"]:
        parts += [c["title"], c["when"], c["meta"]]
    for j in job_entries(R, v):
        parts += [j["co"], j["title"], j["when"], j["meta"]] + j["bullets"]
    for t, bl in project_entries(R, v):
        parts += [t] + bl
    parts += [x for e in R["education"] for x in e]
    for s in R["extras"]:
        for e in s["entries"]:
            parts += [e["title"], e["when"]] + e["bullets"]
    return plain(" \n ".join(parts))


def contact_literals(R):
    """The email and phone exactly as printed, for the PDF 'contains' check."""
    text = plain(" ".join(R["contact"]))
    out = []
    m = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    if m:
        out.append(m.group(0).rstrip("."))
    m = re.search(r"\+?\d[\d ().-]{6,}\d", text)
    if m:
        out.append(m.group(0).strip())
    return out


# ---------- HTML ----------

def _jobline(left, right):
    return f'<div class="jobline"><span>{left}</span><span class="when">{right}</span></div>'


def html_version(R, v):
    with open(CSS_PATH, encoding="utf-8") as f:
        css = f.read()
    t = R["titles"]
    p = [f'<section class="page"><div class="rule"></div><h1>{html.escape(R["name"])}</h1>',
         f'<div class="headline">{v.get("headline", "")}</div>',
         f'<div class="contact">{"<br>".join(R["contact"])}</div>']
    for sec in R["order"]:
        if sec == "summary" and v.get("summary"):
            p.append(f'<h2>{t["summary"]}</h2><p class="summary">{v["summary"]}</p>')
        elif sec == "skills" and skill_lines(R, v):
            p.append(f'<h2>{t["skills"]}</h2><div class="skills">' +
                     "".join(f"<div><b>{a}:</b> {b}</div>" for a, b in skill_lines(R, v)) + "</div>")
        elif sec == "certifications" and R["certs"]:
            p.append(f'<h2>{t["certifications"]}</h2>' + "".join(
                '<div class="cert">' + _jobline(c["title"], c["when"]) +
                (f'<div class="certmeta">{c["meta"]}</div>' if c["meta"] else "") + "</div>" for c in R["certs"]))
        elif sec == "experience":
            jobs = job_entries(R, v)
            if jobs:
                p.append(f'<h2>{t["experience"]}</h2>')
            for j in jobs:
                p.append('<div class="job">' + _jobline(f'{j["co"]} | {j["title"]}', j["when"]) +
                         (f'<div class="certmeta">{j["meta"]}</div>' if j["meta"] else "") +
                         '<ul class="bullets">' + "".join(f"<li>{b}</li>" for b in j["bullets"]) + "</ul></div>")
        elif sec == "projects" and project_entries(R, v):
            p.append(f"<h2>{projects_title(R, v)}</h2>")
            for ti, bl in project_entries(R, v):
                p.append(f'<div class="project"><b>{ti}</b><ul class="bullets">' +
                         "".join(f"<li>{x}</li>" for x in bl) + "</ul></div>")
        elif sec == "education" and R["education"]:
            p.append(f'<h2>{t["education"]}</h2>' + "".join(
                f'<div class="edu"><div class="degree">{d}</div>{s}</div>' for d, s in R["education"]))
        elif sec == "extras":
            for s in R["extras"]:
                p.append(f"<h2>{s['title']}</h2>")
                for e in s["entries"]:
                    head = _jobline(e["title"], e["when"]) if e["when"] else f"<b>{e['title']}</b>"
                    cls = "pub" if e["style"] == "pub" else "bullets"
                    p.append(f'<div class="project">{head}<ul class="{cls}">' +
                             "".join(f"<li>{x}</li>" for x in e["bullets"]) + "</ul></div>")
    p.append("</section>")
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{html.escape(R["name"])} — Resume</title>'
            f"<style>\n{css}</style></head><body>\n" + "\n".join(p) + "\n</body></html>")


# ---------- PDF via headless Chrome (fallback when Tectonic is missing) ----------

CHROME_CANDIDATES = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                     "/Applications/Chromium.app/Contents/MacOS/Chromium",
                     "google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]


def chrome():
    for c in [setting("chrome_path", "")] + CHROME_CANDIDATES:
        if c and (os.path.exists(c) or shutil.which(c)):
            return c if os.path.exists(c) else shutil.which(c)
    raise RuntimeError("Chrome/Chromium not found; set resume_build.chrome_path or install Tectonic")


def to_pdf(html_path, pdf_path):
    with tempfile.TemporaryDirectory() as prof:
        subprocess.run([chrome(), "--headless", "--disable-gpu", f"--user-data-dir={prof}", "--no-pdf-header-footer",
                        f"--print-to-pdf={pdf_path}", "file://" + os.path.abspath(html_path)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)


# ---------- DOCX (same look: Arial, the template colours, blue rules, right-aligned dates) ----------

def have_docx():
    try:
        import docx  # noqa: F401
        return True
    except ImportError:
        return False


def docx_version(R, v, path):
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Inches, Pt, RGBColor

    NAVY, BLUE, GREY, TEXT = (RGBColor(0x15, 0x3B, 0x54), RGBColor(0x17, 0x6F, 0x9C),
                              RGBColor(0x41, 0x5D, 0x70), RGBColor(0x1D, 0x2B, 0x38))
    RIGHT = Inches(7.5)

    def border(par, side, color, size):
        ppr = par._p.get_or_add_pPr()
        bdr = ppr.find(qn("w:pBdr"))
        if bdr is None:
            bdr = OxmlElement("w:pBdr")
            ppr.append(bdr)
        el = OxmlElement(f"w:{side}")
        for k, val in (("val", "single"), ("sz", str(size)), ("space", "1"), ("color", color)):
            el.set(qn(f"w:{k}"), val)
        bdr.append(el)

    def runs(par, text, size=10, color=TEXT, bold=False):
        text = re.sub(r"<br\s*/?>", "\n", re.sub(r"</?a[^>]*>", "", text))
        is_b = is_i = False
        for piece in re.split(r"(</?[bi]>)", text):
            if piece in ("<b>", "</b>"):
                is_b = piece == "<b>"; continue
            if piece in ("<i>", "</i>"):
                is_i = piece == "<i>"; continue
            if not piece:
                continue
            r = par.add_run(html.unescape(piece))
            r.font.size, r.font.color.rgb, r.font.name = Pt(size), color, "Arial"
            r.bold, r.italic = bold or is_b, is_i
            if is_b and color == TEXT:
                r.font.color.rgb = NAVY

    def para(before=0, after=0, align=None):
        par = doc.add_paragraph()
        f = par.paragraph_format
        f.space_before, f.space_after, f.line_spacing = Pt(before), Pt(after), 1.12
        if align is not None:
            par.alignment = align
        return par

    def heading(text):
        par = para(before=10, after=4)
        runs(par, html.unescape(text).upper(), 10.8, BLUE, True)
        border(par, "bottom", "6EA9C6", 6)

    def jobline(left, right, before=7):
        par = para(before=before)
        par.paragraph_format.tab_stops.add_tab_stop(RIGHT, WD_TAB_ALIGNMENT.RIGHT)
        par.paragraph_format.keep_with_next = True
        runs(par, left, 10, BLUE, True)
        par.add_run("\t")
        runs(par, right, 8.5, GREY, True)

    def meta(text):
        runs(para(after=1), text, 8.5, GREY)

    def bullets(items):
        for t in items:
            par = doc.add_paragraph(style="List Bullet")
            f = par.paragraph_format
            f.space_before, f.space_after, f.line_spacing = Pt(1), Pt(1), 1.12
            f.left_indent, f.first_line_indent = Inches(0.21), Inches(-0.16)
            runs(par, t)

    doc = Document()
    s = doc.sections[0]
    s.page_width, s.page_height = Inches(8.5), Inches(11)
    s.top_margin = s.bottom_margin = Inches(0.42)
    s.left_margin = s.right_margin = Inches(0.5)
    st = doc.styles["Normal"]
    st.font.name, st.font.size = "Arial", Pt(10)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), "Arial")

    rule = para(after=6)
    rule.paragraph_format.line_spacing = Pt(2)
    border(rule, "bottom", "168FC6", 16)
    runs(para(after=2, align=WD_ALIGN_PARAGRAPH.CENTER), html.escape(R["name"]), 23, NAVY, True)
    runs(para(after=2, align=WD_ALIGN_PARAGRAPH.CENTER), v.get("headline", ""), 10.2, BLUE, True)
    runs(para(align=WD_ALIGN_PARAGRAPH.CENTER), "<br>".join(R["contact"]), 8.5, GREY)
    t = R["titles"]
    for sec in R["order"]:
        if sec == "summary" and v.get("summary"):
            heading(t["summary"]); runs(para(), v["summary"])
        elif sec == "skills" and skill_lines(R, v):
            heading(t["skills"])
            for a, b in skill_lines(R, v):
                par = para(after=1.5)
                runs(par, a + ": ", 10, BLUE, True)
                runs(par, b)
        elif sec == "certifications" and R["certs"]:
            heading(t["certifications"])
            for i, c in enumerate(R["certs"]):
                jobline(c["title"], c["when"], before=0 if i == 0 else 4)
                if c["meta"]:
                    meta(c["meta"])
        elif sec == "experience" and job_entries(R, v):
            heading(t["experience"])
            for i, j in enumerate(job_entries(R, v)):
                jobline(f'{j["co"]} | {j["title"]}', j["when"], before=0 if i == 0 else 7)
                if j["meta"]:
                    meta(j["meta"])
                bullets(j["bullets"])
        elif sec == "projects" and project_entries(R, v):
            heading(projects_title(R, v))
            for i, (ti, bl) in enumerate(project_entries(R, v)):
                runs(para(before=0 if i == 0 else 6), ti, 10, BLUE, True)
                bullets(bl)
        elif sec == "education" and R["education"]:
            heading(t["education"])
            for d, school in R["education"]:
                runs(para(before=3), d, 10, BLUE, True)
                runs(para(), school)
        elif sec == "extras":
            for sx in R["extras"]:
                heading(sx["title"])
                for i, e in enumerate(sx["entries"]):
                    if e["when"]:
                        jobline(e["title"], e["when"], before=0 if i == 0 else 6)
                    else:
                        runs(para(before=0 if i == 0 else 6), e["title"], 10, BLUE, True)
                    bullets(e["bullets"])
    doc.core_properties.title, doc.core_properties.author = f"{R['name']} — Resume", R["name"]
    doc.save(path)

#!/usr/bin/env python3
"""Turn an HTTrack mirror of learncpp.com into clean, offline lesson pages.

For every lesson it keeps only the title and the lesson body. Everything from
the "Next lesson / Back to table of contents / Previous lesson" block onwards
is dropped, along with the comment section, header, sidebar, footer, ads and
scripts. The site's own stylesheets are kept by default so the coloured
"Best practice" / "Key insight" boxes and code blocks still look right.

The output tree mirrors the HTTrack layout (site/cpp-tutorial/<slug>/index.html)
so every relative image, stylesheet and lesson-to-lesson link keeps working.
A new index.html, ordered by data/learncpp_toc.txt, is written at the top.

Usage:
    python3 scripts/clean.py --mirror mirror --out offline
"""

import argparse
import html
import re
import shutil
import sys
from pathlib import Path

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

SITE_DIR = "www.learncpp.com"

NAV_MARKERS = re.compile(
    r"^\s*(next lesson|previous lesson|back to table of contents)\s*$", re.I
)

# Removed wherever they appear inside the lesson.
JUNK_SELECTORS = [
    "script", "noscript", "iframe", "ins", "form", "object", "embed",
    "#comments", ".comments-area", "#wpdcom", "[id^=wpdiscuz]", "[class*=wpdiscuz]",
    "[id^=ezoic]", "[class*=ezoic]", "[id^=div-gpt-ad]", ".adsbygoogle",
    ".sharedaddy", ".jp-relatedposts", ".entry-footer", ".entry-meta",
]
# Prev/next navigation. Only used as a fallback after the text-based cut,
# which also removes whatever trails the navigation.
NAV_SELECTORS = [".prevnext", "[class*=prevnext]", ".post-navigation", ".nav-links"]
# Ad Inserter blocks: class="code-block code-block-3" (not real code blocks).
AD_INSERTER_CLASS = re.compile(r"^code-block-\d+$")

LESSON_NUM = re.compile(r"^\s*([0-9A-Za-z]{1,3}\.[0-9A-Za-z]{1,3})\s*[—–:-]\s*")
TOC_NUM = re.compile(r"^[0-9A-Za-z]{1,3}\.[0-9A-Za-z]{1,3}$")
TOC_CHAPTER = re.compile(r"^(Chapter|Appendix)\s+\S+$")
TOC_NOISE = {"split", "updated", "moved", "new"}

EXTRA_CSS = """
/* added by clean.py */
html, body { background: #fff; margin: 0; padding: 0; }
.clean-main { max-width: 920px; margin: 0 auto; padding: 1.5rem 1rem 4rem; }
.clean-main article { width: auto !important; float: none !important; margin: 0 !important; }
.clean-main img { max-width: 100%; height: auto; }
.clean-main pre { overflow-x: auto; }
"""

BASIC_CSS = """
body { font-family: system-ui, sans-serif; line-height: 1.6; color: #222; }
h1 { line-height: 1.25; }
pre, code { font-family: ui-monospace, "DejaVu Sans Mono", monospace; }
pre { background: #f6f8fa; border: 1px solid #ddd; padding: .75rem; }
table { border-collapse: collapse; } td, th { border: 1px solid #ccc; padding: .3rem .5rem; }
"""


def norm_title(s):
    s = html.unescape(s).lower()
    s = s.replace("“", '"').replace("”", '"').replace("’", "'")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def parse_toc(path):
    """Return [(chapter_heading, [(number, title), ...]), ...] from the TOC text."""
    lines = [l.strip() for l in Path(path).read_text(encoding="utf-8").splitlines()]
    lines = [l for l in lines if l and l.lower() not in TOC_NOISE]
    chapters = []
    i = 0
    while i < len(lines):
        line = lines[i]
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if TOC_NUM.match(line) and nxt:
            if not chapters:
                chapters.append(("", []))
            chapters[-1][1].append((line, nxt))
            i += 2
        elif TOC_CHAPTER.match(line) and nxt and not TOC_NUM.match(nxt):
            chapters.append((f"{line}: {nxt}", []))
            i += 2
        elif not chapters or chapters[-1][1]:
            # A heading line without "Chapter N" (e.g. the first section).
            chapters.append((line, []))
            i += 1
        else:
            i += 1
    return chapters


def find_title(soup):
    h1 = soup.select_one("h1.entry-title") or soup.select_one("article h1") or soup.find("h1")
    if h1:
        return h1
    return None


def find_content(soup):
    for sel in (".entry-content", "article .post-content", "article", "main", "#content"):
        node = soup.select_one(sel)
        if node:
            return node
    return None


def text_len(node):
    return len(node.get_text(" ", strip=True))


def remove_junk(root, selectors=JUNK_SELECTORS):
    for c in root.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()
    for sel in selectors:
        for node in root.select(sel):
            node.decompose()
    for node in root.find_all(class_=AD_INSERTER_CLASS):
        node.decompose()


def nav_block(root):
    """Smallest element inside root that holds the prev/next navigation."""
    markers = [s for s in root.find_all(string=NAV_MARKERS)]
    if not markers:
        return None
    kinds = {norm_title(m) for m in markers}
    node = markers[0].parent
    # Climb until this element contains every kind of marker that exists,
    # but never let the "block" become a big chunk of the lesson.
    while node is not None and node is not root:
        found = {norm_title(s) for s in node.find_all(string=NAV_MARKERS)}
        if found >= kinds:
            break
        if node.parent is root or text_len(node.parent) > 800:
            break
        node = node.parent
    return node if node is not root else None


def truncate_from(node, root):
    """Delete node and everything after it, up to (not including) root.

    Returns True if the tail was cut, False if only the nav block was removed.
    """
    lesson = text_len(root) - text_len(node)
    after = 0
    doomed = []
    cur = node
    while cur is not None and cur is not root:
        for sib in list(cur.next_siblings):
            doomed.append(sib)
            after += text_len(sib) if isinstance(sib, Tag) else len(str(sib).strip())
        cur = cur.parent
    # Safety net: if the cut would eat a big part of the lesson, the markers
    # were somewhere unexpected; drop only the nav block itself.
    if lesson and after > 0.35 * lesson:
        node.decompose()
        return False
    for sib in doomed:
        sib.extract()
    node.decompose()
    return True


def stylesheet_links(soup):
    links = []
    for link in soup.find_all("link", href=True):
        rel = [r.lower() for r in (link.get("rel") or [])]
        if "stylesheet" in rel and not link["href"].startswith(("http://", "https://", "//")):
            links.append(link["href"])
    return links


def clean_page(src, site_css=True):
    soup = BeautifulSoup(src.read_bytes(), "lxml")
    title_el = find_title(soup)
    content = find_content(soup)
    if title_el is None or content is None:
        return None
    title_text = title_el.get_text(" ", strip=True)

    # Keep the <article> wrapper (minus everything else) so the site's
    # stylesheet selectors still match.
    article = content.find_parent("article") or content
    remove_junk(article)
    nav = nav_block(article)
    cut_clean = truncate_from(nav, article) if nav is not None else None
    remove_junk(article, NAV_SELECTORS)

    # Make sure the title is present even if it lived outside <article>.
    if not article.find("h1"):
        article.insert(0, title_el)

    css_links = stylesheet_links(soup) if site_css else []
    head = [
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{html.escape(title_text)}</title>",
    ]
    head += [f'<link rel="stylesheet" href="{html.escape(h, quote=True)}">' for h in css_links]
    head.append(f"<style>{BASIC_CSS if not css_links else ''}{EXTRA_CSS}</style>")

    out = (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n"
        + "\n".join(head)
        + "\n</head>\n<body>\n<main class=\"clean-main\">\n"
        + str(article)
        + "\n</main>\n</body>\n</html>\n"
    )
    return title_text, out, cut_clean


def lesson_pages(site):
    tut = site / "cpp-tutorial"
    if not tut.is_dir():
        return []
    return sorted(p for p in tut.glob("*/index.html") if p.is_file())


def copy_assets(site, out_site):
    for p in site.rglob("*"):
        if p.is_file() and p.suffix.lower() not in (".html", ".htm"):
            dest = out_site / p.relative_to(site)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dest)


def build_index(chapters, pages, out_dir):
    """pages: list of (number_or_None, title, relpath)."""
    by_num = {n.lower(): (t, r) for n, t, r in pages if n}
    by_title = {norm_title(t): (t, r) for n, t, r in pages}
    used = set()
    missing = []
    parts = []
    for heading, lessons in chapters:
        if heading:
            parts.append(f"<h2>{html.escape(heading)}</h2>")
        parts.append("<ul>")
        for num, title in lessons:
            hit = by_num.get(num.lower()) or by_title.get(norm_title(title))
            label = f"{html.escape(num)} &mdash; {html.escape(title)}"
            if hit:
                used.add(hit[1])
                parts.append(f'<li><a href="{html.escape(hit[1], quote=True)}">{label}</a></li>')
            else:
                missing.append(f"{num} {title}")
                parts.append(f'<li class="missing">{label} <em>(not downloaded)</em></li>')
        parts.append("</ul>")
    extra = [(t, r) for n, t, r in pages if r not in used]
    if extra:
        parts.append("<h2>Other pages</h2><ul>")
        for t, r in sorted(extra):
            parts.append(f'<li><a href="{html.escape(r, quote=True)}">{html.escape(t)}</a></li>')
        parts.append("</ul>")

    doc = (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>LearnCpp offline</title>\n<style>"
        "body{font-family:system-ui,sans-serif;max-width:920px;margin:0 auto;padding:1.5rem 1rem;line-height:1.5}"
        "h2{margin-top:2rem;font-size:1.15rem}ul{padding-left:1.2rem}"
        ".missing{color:#999}a{text-decoration:none}a:hover{text-decoration:underline}"
        "</style>\n</head>\n<body>\n<h1>LearnCpp offline</h1>\n"
        + "\n".join(parts)
        + "\n</body>\n</html>\n"
    )
    (out_dir / "index.html").write_text(doc, encoding="utf-8")
    return missing, extra


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mirror", default="mirror", help="HTTrack output directory (default: mirror)")
    ap.add_argument("--out", default="offline", help="output directory (default: offline)")
    ap.add_argument("--toc", default=str(Path(__file__).resolve().parent.parent / "data" / "learncpp_toc.txt"),
                    help="table of contents text file used to order index.html")
    ap.add_argument("--no-site-css", action="store_true",
                    help="drop learncpp's stylesheets and use a plain built-in style")
    args = ap.parse_args(argv)

    site = Path(args.mirror) / SITE_DIR
    if not site.is_dir():
        sys.exit(f"error: {site} not found; run scripts/mirror.sh first")
    pages_src = lesson_pages(site)
    if not pages_src:
        sys.exit(f"error: no lessons under {site}/cpp-tutorial/*/index.html")

    out_dir = Path(args.out)
    out_site = out_dir / "site"
    if out_site.exists():
        shutil.rmtree(out_site)
    out_site.mkdir(parents=True)
    copy_assets(site, out_site)

    pages, skipped, uncut = [], [], []
    for src in pages_src:
        result = clean_page(src, site_css=not args.no_site_css)
        rel = src.relative_to(site)
        if result is None:
            skipped.append(str(rel))
            continue
        title, doc, cut_clean = result
        if cut_clean is not True:
            uncut.append(str(rel))
        dest = out_site / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(doc, encoding="utf-8")
        m = LESSON_NUM.match(title)
        num = m.group(1) if m else None
        bare_title = LESSON_NUM.sub("", title) if m else title
        pages.append((num, bare_title, f"site/{rel.as_posix()}"))

    chapters = parse_toc(args.toc) if Path(args.toc).is_file() else []
    missing, extra = build_index(chapters, pages, out_dir)
    # Lessons sometimes link to the site root; send those to our index.
    (out_site / "index.html").write_text(
        '<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0; url=../index.html">'
        '<a href="../index.html">Table of contents</a>\n', encoding="utf-8")

    print(f"Cleaned {len(pages)} lesson pages into {out_dir}/ (open {out_dir}/index.html)")
    if skipped:
        print(f"Skipped {len(skipped)} pages with no title/content: " + ", ".join(skipped[:10]))
    if uncut:
        print(f"{len(uncut)} pages had no clear next/previous block to cut at; check them: "
              + ", ".join(uncut[:10]))
    if missing:
        print(f"{len(missing)} TOC entries were not found in the mirror:")
        for m in missing[:30]:
            print(f"  - {m}")
        if len(missing) > 30:
            print(f"  ... and {len(missing) - 30} more (marked 'not downloaded' in index.html)")
    if extra:
        print(f"{len(extra)} downloaded pages are not in the TOC (listed under 'Other pages').")


if __name__ == "__main__":
    main()

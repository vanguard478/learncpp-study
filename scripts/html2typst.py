#!/usr/bin/env python3
"""Convert a cleaned learncpp lesson (output of clean.py) into Typst markup.

The generated markup calls into the Typst library typst/learncpp.typ
(lesson-title, callout, lc-image), so styling lives in one place and the
lesson files stay plain.

Library use:
    from html2typst import Context, convert_lesson
    result = convert_lesson(html_text, Context(page="cpp-tutorial/comments/index.html"))
    result.markup   # Typst source for the lesson body
    result.images   # site-relative image paths the markup refers to

Command line (handy for checking a single page):
    python3 scripts/html2typst.py offline/site/cpp-tutorial/comments/index.html
"""

import posixpath
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

SITE_URL = "https://www.learncpp.com/"
LESSON_NUM = re.compile(r"^\s*([0-9A-Za-z]{1,3}\.[0-9A-Za-z]{1,3})\s*[\u2014\u2013:-]\s*")

# Characters that always mean something in Typst markup.
_ALWAYS = set('\\#*_`$<>@[]~')
# Marks the end of an inline function call; see _finish_inline().
_CALL_END = "\ue000"

# Callout labels used on learncpp, mapped to the kinds learncpp.typ knows.
CALLOUT_KINDS = {
    "best practice": "best-practice",
    "key insight": "insight",
    "warning": "warning",
    "tip": "tip",
    "note": "note",
    "author's note": "note",
    "nomenclature": "nomenclature",
    "for advanced readers": "advanced",
    "related content": "related",
    "as an aside": "aside",
    "for gcc/clang users": "compiler",
    "for visual studio users": "compiler",
    "for gcc users": "compiler",
    "for clang users": "compiler",
    "rule": "warning",
    "solution": "solution",
}
CALLOUT_CLASS = re.compile(r"note|callout|background|topline|insight|bestpractice|warning|tip|aside", re.I)
SOLUTION_CLASS = re.compile(r"solution|spoiler", re.I)
SOLUTION_TOGGLE = re.compile(r"^\s*(show|hide)\s+solution\s*$", re.I)

SKIP_TAGS = {"script", "style", "noscript", "iframe", "button", "input", "select", "textarea",
             "form", "svg", "canvas", "video", "audio", "object", "embed", "template", "link", "meta"}
BLOCK_TAGS = {"p", "div", "section", "article", "main", "aside", "header", "footer", "nav",
              "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "dl", "pre", "table", "blockquote",
              "figure", "figcaption", "hr", "center"}


@dataclass
class Context:
    """Information about the page being converted.

    page:         site-relative path of the HTML page, e.g. "cpp-tutorial/x/index.html";
                  used to resolve relative links and image paths.
    lesson_slugs: lessons that will be part of the document; links to them become
                  internal Typst links (<lesson-SLUG>), anything else links to learncpp.com.
    image_path:   maps a site-relative image path to the path written in the .typ
                  file, or None if the image isn't available (a placeholder is used).
    """
    page: str = "cpp-tutorial/page/index.html"
    lesson_slugs: set = field(default_factory=set)
    image_path: object = staticmethod(lambda site_path: None)


@dataclass
class Result:
    number: str | None
    title: str
    slug: str
    markup: str
    images: list


# ---------------------------------------------------------------- escaping

def escape_text(s):
    """Escape plain text for Typst markup (whitespace already collapsed)."""
    out = []
    n = len(s)
    for i, ch in enumerate(s):
        nxt = s[i + 1] if i + 1 < n else ""
        if ch in _ALWAYS:
            out.append("\\" + ch)
        elif ch == "/" and nxt in "/*":           # comment starters
            out.append("\\/")
        elif ch == "-" and nxt in "-?":           # en/em dash, soft hyphen shorthands
            out.append("\\-")
        else:
            out.append(ch)
    return "".join(out)


def tstr(s):
    """A Typst string literal."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def fix_line_start(line):
    """Escape characters that would start a heading/list/term at the start of a line."""
    if re.match(r"^(=|[-+](\s|$)|/\s)", line):
        return "\\" + line
    m = re.match(r"^(\d+)\.(\s|$)", line)
    if m:
        return m.group(1) + "\\." + line[m.end(1) + 1:]
    return line


def _finish_inline(s):
    s = re.sub(r"[ \t\r\n\f]+", " ", s)
    # After a function call such as #strong[..] or #raw(..), a following
    # "(", "[" or "." would be read as part of the call; escape it.
    s = re.sub(_CALL_END + r"([(\[.])", r"\\\1", s)
    return s.replace(_CALL_END, "")


def _call(name, body):
    """#name[body] with leading/trailing spaces moved outside the brackets."""
    lead = " " if body[:1].isspace() else ""
    trail = " " if body[-1:].isspace() else ""
    body = body.strip()
    if not body:
        return lead or trail
    return f"{lead}#{name}[{body}]{_CALL_END}{trail}"


# ---------------------------------------------------------------- helpers

def classes(tag):
    return " ".join(tag.get("class") or [])


def is_hidden(tag):
    style = (tag.get("style") or "").replace(" ", "").lower()
    return "display:none" in style


def raw_inline(code):
    code = re.sub(r"[ \t\r\n\f]+", " ", code)
    if code and "`" not in code and not code.startswith(" ") and not code.endswith(" "):
        return f"`{code}`"
    return f"#raw({tstr(code)}){_CALL_END}"


def code_lang(tag, code):
    names = " ".join(classes(t) for t in [tag, *tag.find_all(True)][:3]).lower()
    m = re.search(r"(?:language|lang)-([\w+#-]+)", names)
    if m:
        lang = m.group(1)
        return "cpp" if lang in ("c++", "cplusplus") else lang
    if "cpp" in names or "c++" in names:
        return "cpp"
    if re.search(r"#include|\bint main\s*\(|std::|;\s*$", code, re.M):
        return "cpp"
    return ""


def pre_text(pre):
    pre = pre.__copy__()
    for gutter in pre.find_all(class_=re.compile(r"line-?num|gutter|lineno", re.I)):
        gutter.decompose()
    for br in pre.find_all("br"):
        br.replace_with("\n")
    text = pre.get_text()
    lines = [l.rstrip() for l in text.replace("\r\n", "\n").split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def raw_block(code, lang):
    fence = "```"
    while fence in code:
        fence += "`"
    return f"{fence}{lang}\n{code}\n{fence}"


def clean_label(text):
    """'As an aside...' / 'Best practice:' -> 'As an aside' / 'Best practice'."""
    return re.sub(r"[\s:.\u2026]+$", "", text)


def indent(text, prefix):
    return "\n".join(prefix + l if l.strip() else "" for l in text.split("\n"))


# ---------------------------------------------------------------- converter

class Converter:
    def __init__(self, ctx):
        self.ctx = ctx
        self.page_dir = posixpath.dirname(ctx.page)
        self.images = []
        self.heading_shift = 0

    # ---- links and images

    def resolve(self, url):
        """Return ("lesson", slug) | ("url", absolute) | ("site", site_path) | (None, None)."""
        if not url or url.startswith(("javascript:", "mailto:")):
            return (None, None) if not url or url.startswith("javascript:") else ("url", url)
        parts = urlsplit(url)
        if parts.scheme in ("http", "https"):
            host = parts.netloc.lower()
            if host.endswith("learncpp.com"):
                path = parts.path.lstrip("/")
            else:
                return ("url", url)
        elif parts.scheme:
            return ("url", url)
        elif not parts.path:          # "#anchor" on the same page
            return (None, None)
        else:
            path = posixpath.normpath(posixpath.join(self.page_dir, unquote(parts.path)))
        if path.startswith("../"):
            return (None, None)
        m = re.match(r"^cpp-tutorial/([^/]+)(?:/(?:index\.html?)?)?$", path)
        if m:
            return ("lesson", m.group(1))
        return ("site", path)

    def link(self, tag, body):
        kind, target = self.resolve(tag.get("href", "").strip())
        if not body.strip():
            return body
        if kind == "lesson":
            if target in self.ctx.lesson_slugs:
                return f"#link(<lesson-{target}>)[{body.strip()}]{_CALL_END}"
            target = f"{SITE_URL}cpp-tutorial/{target}/"
        elif kind == "site":
            target = SITE_URL + re.sub(r"(^|/)index\.html?$", r"\1", target)
        elif kind is None:
            return body
        return f"#link({tstr(target)})[{body.strip()}]{_CALL_END}"

    def image(self, tag):
        src = tag.get("src") or tag.get("data-src") or ""
        kind, target = self.resolve(src.strip())
        alt = (tag.get("alt") or "").strip()
        path = self.ctx.image_path(target) if kind == "site" else None
        if path is None:
            label = alt or (posixpath.basename(urlsplit(src).path) if src else "image")
            return f"#missing-image({tstr(label)}){_CALL_END}"
        self.images.append(target)
        args = [tstr(path)]
        width = tag.get("width", "")
        if width.isdigit():
            args.append(f"width: {int(width) * 0.75:g}pt")
        return f"#lc-image({', '.join(args)}){_CALL_END}"

    # ---- inline content

    def inline(self, node):
        if isinstance(node, Comment):
            return ""
        if isinstance(node, NavigableString):
            return escape_text(re.sub(r"[ \t\r\n\f]+", " ", str(node)))
        if not isinstance(node, Tag) or node.name in SKIP_TAGS or is_hidden(node):
            return ""
        name = node.name
        if SOLUTION_TOGGLE.match(node.get_text()):
            return ""
        if name == "br":
            return f"#linebreak(){_CALL_END}"
        if name == "img":
            return self.image(node)
        if name in ("code", "kbd", "tt", "samp", "var"):
            return raw_inline(node.get_text())
        inner = "".join(self.inline(c) for c in node.children)
        if name in ("strong", "b"):
            return _call("strong", inner)
        if name in ("em", "i", "cite", "dfn"):
            return _call("emph", inner)
        if name in ("u", "ins"):
            return _call("underline", inner)
        if name in ("s", "del", "strike"):
            return _call("strike", inner)
        if name == "sub":
            return _call("sub", inner)
        if name == "sup":
            return _call("super", inner)
        if name == "mark":
            return _call("highlight", inner)
        if name == "a":
            return self.link(node, inner)
        if name in BLOCK_TAGS:
            return f" {inner} "
        return inner

    def paragraph(self, nodes, line_start=True):
        text = _finish_inline("".join(self.inline(n) for n in nodes)).strip()
        return fix_line_start(text) if text and line_start else text

    # ---- blocks

    def blocks(self, node):
        """Convert the children of node into a list of Typst blocks."""
        out, run = [], []

        def flush():
            if run:
                p = self.paragraph(run)
                if p:
                    out.append(p)
                run.clear()

        for child in node.children:
            if isinstance(child, Comment):
                continue
            if isinstance(child, Tag) and child.name in BLOCK_TAGS:
                flush()
                out.extend(self.block(child))
            else:
                run.append(child)
        flush()
        return out

    def block(self, tag):
        name = tag.name
        if name in SKIP_TAGS or is_hidden(tag) and not SOLUTION_CLASS.search(classes(tag)):
            return []
        if SOLUTION_TOGGLE.match(tag.get_text()):
            return []
        if re.fullmatch(r"h[1-6]", name):
            level = min(6, max(3, int(name[1]) + self.heading_shift))
            text = self.paragraph(tag.children, line_start=False)
            return [f"{'=' * level} {text}"] if text else []
        if name == "pre":
            code = pre_text(tag)
            return [raw_block(code, code_lang(tag, code))] if code.strip() else []
        if name in ("ul", "ol"):
            return [self.list_(tag)] if tag.find("li") else []
        if name == "dl":
            return self.deflist(tag)
        if name == "table":
            return [self.table(tag)]
        if name == "hr":
            return ["#line(length: 100%, stroke: 0.5pt + gray)"]
        if name == "blockquote":
            return [f"#quote(block: true)[\n{self.join(self.blocks(tag))}\n]"]
        if name == "figcaption":
            p = self.paragraph(tag.children)
            return [f"#align(center, emph[{p}])"] if p else []
        if name == "p":
            imgs = tag.find_all("img")
            if imgs and not tag.get_text(strip=True):
                return [f"#align(center)[{self.paragraph(tag.children)}]"]
            p = self.paragraph(tag.children)
            return [p] if p else []
        callout = self.callout(tag)
        if callout:
            return callout
        if not any(isinstance(c, Tag) and c.name in BLOCK_TAGS for c in tag.children):
            p = self.paragraph(tag.children)
            return [p] if p else []
        return self.blocks(tag)

    def callout(self, tag):
        if tag.name not in ("div", "aside", "section"):
            return None
        cls = classes(tag)
        title_el = self._callout_title(tag)
        title = clean_label(title_el.get_text(" ", strip=True)) if title_el is not None else None
        kind = None
        if title:
            key = title.lower()
            kind = CALLOUT_KINDS.get(key)
            if kind is None and key.startswith("q:"):
                kind, title = "faq", None
            if kind is None and CALLOUT_CLASS.search(cls):
                kind = "note"
        if SOLUTION_CLASS.search(cls):
            kind, title = "solution", title or "Solution"
        if kind is None and CALLOUT_CLASS.search(cls):
            kind = "note"
            title_el = title = None
        if kind is None:
            return None
        if title_el is not None and title:
            title_el.extract()
        body = self.join(self.blocks(tag))
        if not body.strip() and not title:
            return []
        args = [f"kind: {tstr(kind)}"]
        if title:
            args.append(f"title: {tstr(title)}")
        return [f"#callout({', '.join(args)})[\n{body}\n]"]

    def _callout_title(self, tag):
        first = next((c for c in tag.children if isinstance(c, Tag)), None)
        if first is None:
            return None
        # The label may be wrapped, e.g. <p><strong>Best practice</strong></p>.
        text = first.get_text(" ", strip=True)
        if not text or len(text) > 60:
            return None
        if "title" in classes(first) or clean_label(text).lower() in CALLOUT_KINDS:
            return first
        if text.lower().startswith("q:"):
            return first
        return None

    def list_(self, tag):
        marker = "+" if tag.name == "ol" else "-"
        items = []
        for li in tag.find_all("li", recursive=False):
            body = self.join(self.blocks(li)) or ""
            lines = body.split("\n")
            first = lines[0]
            rest = indent("\n".join(lines[1:]), "  ") if len(lines) > 1 else ""
            items.append(f"{marker} {first}" + (f"\n{rest}" if rest else ""))
        start = tag.get("start", "")
        if tag.name == "ol" and start.isdigit() and start != "1" and items:
            items[0] = f"{start}." + items[0][1:]      # "3. item"; later "+" items continue from it
        return "\n".join(items)

    def deflist(self, tag):
        out = []
        for child in tag.find_all(["dt", "dd"], recursive=False):
            p = self.join(self.blocks(child))
            if not p:
                continue
            out.append(f"#strong[{p}]" if child.name == "dt" else indent(p, "  "))
        return out

    def table(self, tag):
        rows = [tr for tr in tag.find_all("tr") if tr.find_parent("table") is tag]
        if not rows:
            return ""
        ncols = max(sum(int(c.get("colspan", 1) or 1) for c in tr.find_all(["td", "th"], recursive=False))
                    for tr in rows)
        header, body = [], []
        for tr in rows:
            cells = []
            for cell in tr.find_all(["td", "th"], recursive=False):
                content = self.join(self.blocks(cell))
                cs, rs = int(cell.get("colspan", 1) or 1), int(cell.get("rowspan", 1) or 1)
                args = []
                if cs > 1:
                    args.append(f"colspan: {cs}")
                if rs > 1:
                    args.append(f"rowspan: {rs}")
                cells.append(f"table.cell({', '.join(args)})[{content}]" if args else f"[{content}]")
            in_head = tr.find_parent("thead") is not None or all(c.name == "th" for c in tr.find_all(["td", "th"], recursive=False))
            (header if in_head and not body else body).append(", ".join(cells))
        parts = [f"  columns: {max(ncols, 1)},"]
        if header:
            parts.append("  table.header(" + ", ".join(header) + "),")
        parts += [f"  {row}," for row in body if row]
        return "#lc-table(\n" + "\n".join(parts) + "\n)"

    @staticmethod
    def join(blocks):
        return "\n\n".join(b for b in blocks if b and b.strip())


# ---------------------------------------------------------------- entry points

def convert_lesson(html_text, ctx):
    """Convert one cleaned lesson page. Returns a Result."""
    soup = BeautifulSoup(html_text, "lxml")
    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()
    h1 = soup.select_one("h1.entry-title") or soup.find("h1")
    full_title = h1.get_text(" ", strip=True) if h1 else ""
    m = LESSON_NUM.match(full_title)
    number = m.group(1) if m else None
    title = LESSON_NUM.sub("", full_title) if m else full_title
    if h1:
        header = h1.find_parent("header")
        (header if header and len(header.get_text(strip=True)) <= len(full_title) + 5 else h1).decompose()

    root = soup.select_one(".entry-content") or soup.find("article") or soup.find("main") or soup.body or soup
    conv = Converter(ctx)
    levels = [int(h.name[1]) for h in root.find_all(re.compile(r"^h[2-6]$"))]
    conv.heading_shift = 3 - min(levels) if levels else 0

    slug = posixpath.basename(posixpath.dirname(ctx.page))
    head = f"#lesson-title({tstr(number) if number else 'none'}, {tstr(title)}, {tstr(slug)})"
    body = conv.join(conv.blocks(root))
    markup = '#import "../learncpp.typ": *\n\n' + head + "\n\n" + body + "\n"
    return Result(number=number, title=title, slug=slug, markup=markup, images=conv.images)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Convert one cleaned lesson HTML file to Typst (prints to stdout).")
    ap.add_argument("html", help="e.g. offline/site/cpp-tutorial/<slug>/index.html")
    args = ap.parse_args(argv)
    path = Path(args.html)
    page = "/".join(path.parts[-3:]) if len(path.parts) >= 3 else path.name
    sys.stdout.write(convert_lesson(path.read_text(encoding="utf-8"), Context(page=page)).markup)


if __name__ == "__main__":
    main()

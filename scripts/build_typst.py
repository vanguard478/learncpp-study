#!/usr/bin/env python3
"""Build a Typst study guide from the cleaned lessons (output of clean.py).

Writes:
    study-guide/learncpp.typ        the Typst library (copied from typst/learncpp.typ)
    study-guide/main.typ            title page, contents, chapters, #include of every lesson
    study-guide/lessons/*.typ       one file per lesson, in TOC order
    study-guide/media/...           images used by the lessons

Usage:
    python3 scripts/build_typst.py                 # offline/ -> study-guide/
    python3 scripts/build_typst.py --compile       # also run `typst compile` -> study-guide/main.pdf
    python3 scripts/build_typst.py --only 1.1 1.2 2.x   # just these lessons (quick previews)
"""

import argparse
import posixpath
import re
import shutil
import subprocess
import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from clean import LESSON_NUM, norm_title, parse_toc  # noqa: E402
from html2typst import Context, convert_lesson, tstr  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}


def read_lessons(site):
    """[(site_relative_page, number, title)] for every cleaned lesson."""
    lessons = []
    for page in sorted((site / "cpp-tutorial").glob("*/index.html")):
        soup = BeautifulSoup(page.read_bytes(), "lxml")
        h1 = soup.select_one("h1.entry-title") or soup.find("h1")
        if not h1:
            continue
        full = h1.get_text(" ", strip=True)
        m = LESSON_NUM.match(full)
        lessons.append((page.relative_to(site).as_posix(), m.group(1) if m else None,
                        LESSON_NUM.sub("", full) if m else full))
    return lessons


def order_by_toc(lessons, chapters):
    """Group lessons as [(chapter_label, chapter_title, [page, ...])] in TOC order."""
    by_num = {n.lower(): p for p, n, _ in lessons if n}
    by_title = {norm_title(t): p for p, _, t in lessons}
    used, groups = set(), []
    for heading, entries in chapters:
        label, _, title = heading.partition(": ")
        if not title:
            label, title = "", heading
        pages = []
        for num, t in entries:
            page = by_num.get(num.lower()) or by_title.get(norm_title(t))
            if page and page not in used:
                used.add(page)
                pages.append(page)
        if pages:
            groups.append((label, title, pages))
    rest = [p for p, _, _ in lessons if p not in used]
    if rest:
        groups.append(("", "Other pages", rest))
    return groups


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", default="offline", help="clean.py output directory (default: offline)")
    ap.add_argument("--out", default="study-guide", help="output directory (default: study-guide)")
    ap.add_argument("--toc", default=str(REPO / "data" / "learncpp_toc.txt"))
    ap.add_argument("--title", default="LearnCpp Study Guide")
    ap.add_argument("--only", nargs="+", metavar="NUM", help="only these lesson numbers, e.g. 1.1 1.x")
    ap.add_argument("--compile", action="store_true", help="run `typst compile` on the result")
    args = ap.parse_args(argv)

    site = Path(args.offline) / "site"
    if not (site / "cpp-tutorial").is_dir():
        sys.exit(f"error: {site}/cpp-tutorial not found; run scripts/clean.py first")
    lessons = read_lessons(site)
    if args.only:
        wanted = {n.lower() for n in args.only}
        lessons = [l for l in lessons if l[1] and l[1].lower() in wanted]
    if not lessons:
        sys.exit("error: no lessons to convert")

    chapters = parse_toc(args.toc) if Path(args.toc).is_file() else []
    groups = order_by_toc(lessons, chapters)
    slugs = {posixpath.basename(posixpath.dirname(p)) for p, _, _ in lessons}

    out = Path(args.out)
    for sub in ("lessons", "media"):
        if (out / sub).exists():
            shutil.rmtree(out / sub)
    (out / "lessons").mkdir(parents=True)
    shutil.copy2(REPO / "typst" / "learncpp.typ", out / "learncpp.typ")

    def image_path(site_path):
        src = site / site_path
        if not src.is_file() or src.suffix.lower() not in IMAGE_EXT:
            return None
        dest = out / "media" / site_path
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        return "/media/" + site_path   # root-relative: image() runs inside learncpp.typ

    main_lines = ['#import "learncpp.typ": *', "",
                  f"#show: guide.with(title: {tstr(args.title)})", ""]
    seq, missing_images = 0, 0
    for label, title, pages in groups:
        main_lines.append(f"#chapter({tstr(label)}, {tstr(title)})")
        for page in pages:
            seq += 1
            ctx = Context(page=page, lesson_slugs=slugs, image_path=image_path)
            result = convert_lesson((site / page).read_text(encoding="utf-8"), ctx)
            missing_images += result.markup.count("#missing-image(")
            name = f"{seq:03d}_{result.slug}.typ"
            (out / "lessons" / name).write_text(result.markup, encoding="utf-8")
            main_lines.append(f'#include "lessons/{name}"')
        main_lines.append("")
    (out / "main.typ").write_text("\n".join(main_lines), encoding="utf-8")

    print(f"Wrote {seq} lessons in {len(groups)} chapters to {out}/ (entry point: {out}/main.typ)")
    if missing_images:
        print(f"{missing_images} images were not in the mirror; they show as placeholders.")

    if args.compile:
        typst = shutil.which("typst")
        if not typst:
            sys.exit("typst not found; install it (e.g. `cargo install --locked typst-cli`) or drop --compile")
        pdf = out / "main.pdf"
        r = subprocess.run([typst, "compile", str(out / "main.typ"), str(pdf)])
        if r.returncode:
            sys.exit(r.returncode)
        print(f"Compiled {pdf}")
    else:
        print(f"Compile with: typst compile {out}/main.typ   (or `typst watch` while editing learncpp.typ)")


if __name__ == "__main__":
    main()

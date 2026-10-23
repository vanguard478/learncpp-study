# learncpp-study

Offline, distraction-free copy of the [learncpp.com](https://www.learncpp.com/) lessons for personal study,
turned into a [Typst](https://typst.app/) study guide.

```
learncpp.com --mirror.sh--> mirror/ --clean.py--> offline/ --build_typst.py--> study-guide/ --typst--> PDF
                 (HTTrack)              (strip page chrome)     (HTML -> .typ)
```

Each lesson keeps only its title and body. The header, sidebar, ads, the
**Next lesson / Back to table of contents / Previous lesson** buttons, everything
after them, and the comment section are removed.

## Requirements (Linux)

```sh
sudo apt install httrack python3-bs4 python3-lxml   # Debian/Ubuntu
# Fedora: sudo dnf install httrack python3-beautifulsoup4 python3-lxml
# Arch:   sudo pacman -S httrack python-beautifulsoup4 python-lxml
```

Plus the Typst CLI for the PDF: `cargo install --locked typst-cli`, your distro's `typst` package,
or a binary from <https://github.com/typst/typst/releases>.

## Usage

```sh
# 1. Download the TOC page, all lessons, and their images/CSS (~a few hundred pages, rate limited)
scripts/mirror.sh            # -> mirror/

# 2. Strip everything but the lesson content
python3 scripts/clean.py     # -> offline/

xdg-open offline/index.html

# 3. Convert to a Typst study guide and compile it
python3 scripts/build_typst.py --compile   # -> study-guide/main.pdf
```

- `offline/index.html` is a table of contents ordered by `data/learncpp_toc.txt`.
  Lessons HTTrack didn't fetch are greyed out and listed in the script output.
- Lesson-to-lesson links, images and the site's styling (code blocks, "Best practice" boxes) work offline.
- `python3 scripts/clean.py --no-site-css` drops learncpp's stylesheets for a plain look.
- Re-run `scripts/mirror.sh` later to update the mirror, then `clean.py` again.

## How the cleanup works

`clean.py` takes the `<article>` from each `mirror/www.learncpp.com/cpp-tutorial/*/index.html`,
finds the block holding the "Next lesson" / "Previous lesson" / "Back to table of contents"
labels and cuts it plus everything after it, then removes comments, ads and scripts.
If a page has no such block, or the cut would remove a large part of the lesson, it only
removes the navigation and lists the page in its output so you can check it.

## Typst study guide

```
study-guide/
├── main.typ        title page, contents, chapters, #include of each lesson (TOC order)
├── learncpp.typ    the Typst library: page style, callouts, code blocks, tables, images
├── lessons/        one .typ per lesson, e.g. 003_introduction-to-functions.typ
└── media/          images used by the lessons
```

- **Change the look in `typst/learncpp.typ`**, not in `study-guide/` (that directory is regenerated,
  and the library is copied in on every build). `typst watch study-guide/main.typ` previews edits live.
- `build_typst.py --only 1.1 1.2 1.x` converts just those lessons, for quick checks.
- Lesson files are readable Typst: learncpp's boxes become `#callout(kind: "best-practice", ...)[...]`,
  code becomes ```` ```cpp ```` blocks, links between lessons become internal PDF links, and quiz
  solutions become "Solution" callouts.
- To debug a single page: `python3 scripts/html2typst.py offline/site/cpp-tutorial/<slug>/index.html`.

The conversion lives in `scripts/html2typst.py` (importable: `convert_lesson(html, Context(...))`);
`scripts/build_typst.py` only handles ordering, images and file layout.
Tests: `python3 -m unittest discover tests` (the compile test runs only if `typst` is installed).

# learncpp-study

Offline, distraction-free copy of the [learncpp.com](https://www.learncpp.com/) lessons for personal study.

Each lesson keeps only its title and body. The header, sidebar, ads, the
**Next lesson / Back to table of contents / Previous lesson** buttons, everything
after them, and the comment section are removed.

## Requirements (Linux)

```sh
sudo apt install httrack python3-bs4 python3-lxml   # Debian/Ubuntu
# Fedora: sudo dnf install httrack python3-beautifulsoup4 python3-lxml
# Arch:   sudo pacman -S httrack python-beautifulsoup4 python-lxml
```

## Usage

```sh
# 1. Download the TOC page, all lessons, and their images/CSS (~a few hundred pages, rate limited)
scripts/mirror.sh            # -> mirror/

# 2. Strip everything but the lesson content
python3 scripts/clean.py     # -> offline/

xdg-open offline/index.html
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

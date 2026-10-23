"""Unit tests for scripts/html2typst.py.  Run: python3 -m unittest discover tests"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from html2typst import Context, convert_lesson, escape_text, fix_line_start  # noqa: E402


def lesson(body, title="2.1 &#8212; Introduction to functions", **ctx):
    html = (f'<html><body><article><header class="entry-header"><h1 class="entry-title">{title}</h1></header>'
            f'<div class="entry-content">{body}</div></article></body></html>')
    ctx.setdefault("page", "cpp-tutorial/introduction-to-functions/index.html")
    return convert_lesson(html, Context(**ctx))


def body_of(result):
    return result.markup.split("\n\n", 2)[2].strip()


class Escaping(unittest.TestCase):
    def test_markup_characters(self):
        self.assertEqual(escape_text("#include <x> a_b *p $5 @u [0] ~"),
                         r"\#include \<x\> a\_b \*p \$5 \@u \[0\] \~")

    def test_comments_and_dashes(self):
        self.assertEqual(escape_text("a // b /* c */ x-- -?"), r"a \// b \/\* c \*/ x\-- \-?")

    def test_line_start(self):
        self.assertEqual(fix_line_start("1. not a list"), r"1\. not a list")
        self.assertEqual(fix_line_start("- dash"), r"\- dash")
        self.assertEqual(fix_line_start("= eq"), r"\= eq")
        self.assertEqual(fix_line_start("x - y"), "x - y")

    def test_text_after_call_is_escaped(self):
        out = body_of(lesson("<p><strong>int</strong>(5) and <strong>s</strong>.size()</p>"))
        self.assertEqual(out, r"#strong[int]\(5) and #strong[s]\.size()")


class Structure(unittest.TestCase):
    def test_title(self):
        r = lesson("<p>x</p>")
        self.assertEqual((r.number, r.title, r.slug), ("2.1", "Introduction to functions", "introduction-to-functions"))
        self.assertIn('#lesson-title("2.1", "Introduction to functions", "introduction-to-functions")', r.markup)

    def test_headings_start_at_level_3(self):
        out = body_of(lesson("<h2>A</h2><h3>B</h3>"))
        self.assertEqual(out, "=== A\n\n==== B")

    def test_code_block(self):
        out = body_of(lesson('<pre><span class="line-number">1</span>#include &lt;iostream&gt;\nint main() {}</pre>'))
        self.assertEqual(out, "```cpp\n#include <iostream>\nint main() {}\n```")

    def test_inline_code(self):
        self.assertEqual(body_of(lesson("<p><code>a`b</code> <code>x</code></p>")), '#raw("a`b") `x`')

    def test_callout_by_label(self):
        out = body_of(lesson('<div class="cpp-note"><p class="cpp-note-title">Best practice</p><p>Do it.</p></div>'))
        self.assertEqual(out, '#callout(kind: "best-practice", title: "Best practice")[\nDo it.\n]')

    def test_plain_div_is_not_callout(self):
        self.assertEqual(body_of(lesson("<div><p>Hello</p></div>")), "Hello")

    def test_hidden_solution(self):
        out = body_of(lesson('<p><a href="#">Show Solution</a></p>'
                             '<div class="cpp-solution" style="display:none"><p>42</p></div>'))
        self.assertEqual(out, '#callout(kind: "solution", title: "Solution")[\n42\n]')

    def test_ordered_list_start(self):
        out = body_of(lesson('<ol start="3"><li>a</li><li>b</li></ol>'))
        self.assertEqual(out, "3. a\n+ b")

    def test_table(self):
        out = body_of(lesson("<table><tr><th>A</th><th>B</th></tr><tr><td colspan='2'>x</td></tr></table>"))
        self.assertIn("columns: 2,", out)
        self.assertIn("table.header([A], [B]),", out)
        self.assertIn("table.cell(colspan: 2)[x],", out)


class Links(unittest.TestCase):
    def test_lesson_links(self):
        body = ('<p><a href="../comments/index.html">in</a> '
                '<a href="https://www.learncpp.com/cpp-tutorial/other/">out</a> '
                '<a href="https://example.com/">ext</a> <a href="#x">anchor</a></p>')
        out = body_of(lesson(body, lesson_slugs={"comments"}))
        self.assertEqual(out, '#link(<lesson-comments>)[in] '
                              '#link("https://www.learncpp.com/cpp-tutorial/other/")[out] '
                              '#link("https://example.com/")[ext] anchor')

    def test_images(self):
        body = '<p><img src="../../images/a.png" width="100"></p><p>x <img src="../../images/b.png" alt="b"></p>'
        r = lesson(body, image_path=lambda p: "/media/" + p if p.endswith("a.png") else None)
        self.assertEqual(r.images, ["images/a.png"])
        self.assertEqual(body_of(r), '#align(center)[#lc-image("/media/images/a.png", width: 75pt)]\n\n'
                                     'x #missing-image("b")')


@unittest.skipUnless(shutil.which("typst"), "typst not installed")
class Compiles(unittest.TestCase):
    def test_tricky_lesson_compiles(self):
        body = ("<p>#include &lt;x&gt; a // b x-- <strong>s</strong>.size() 1. $ @ [ ] ~ \\</p>"
                "<ul><li>a<pre>int x{};</pre></li></ul>"
                '<div class="cpp-note"><p><strong>Warning</strong></p><p>w</p></div>')
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            shutil.copy2(REPO / "typst" / "learncpp.typ", d / "learncpp.typ")
            (d / "lessons").mkdir()
            (d / "lessons" / "l.typ").write_text(lesson(body).markup)
            (d / "main.typ").write_text('#import "learncpp.typ": *\n#show: guide\n#include "lessons/l.typ"\n')
            r = subprocess.run(["typst", "compile", str(d / "main.typ")], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()

// Typst library for the learncpp study guide.
//
// Every generated lesson file imports this, and main.typ applies `guide`.
// Change the look of the whole guide here; scripts/build_typst.py copies this
// file into the output directory on every build.

#let palette = (
  "best-practice": (color: rgb("#2e7d32"), title: "Best practice"),
  "insight":       (color: rgb("#1565c0"), title: "Key insight"),
  "warning":       (color: rgb("#c62828"), title: "Warning"),
  "tip":           (color: rgb("#00838f"), title: "Tip"),
  "note":          (color: rgb("#546e7a"), title: none),
  "nomenclature":  (color: rgb("#6a1b9a"), title: "Nomenclature"),
  "advanced":      (color: rgb("#4527a0"), title: "For advanced readers"),
  "related":       (color: rgb("#455a64"), title: "Related content"),
  "aside":         (color: rgb("#795548"), title: "As an aside"),
  "compiler":      (color: rgb("#ef6c00"), title: none),
  "faq":           (color: rgb("#3949ab"), title: none),
  "solution":      (color: rgb("#558b2f"), title: "Solution"),
)

// Start each lesson on a new page (except the first one in a chapter).
#let lesson-pagebreak = state("lc-lesson-pagebreak", true)
#let after-chapter = state("lc-after-chapter", false)

#let guide(title: "LearnCpp Study Guide", lesson-pagebreak-on: true, body) = {
  set document(title: title)
  set page(paper: "a4", margin: (x: 2cm, y: 2.2cm), numbering: "1")
  set text(font: ("Libertinus Serif", "New Computer Modern"), size: 10.5pt, lang: "en")
  set par(justify: true, leading: 0.62em, spacing: 0.95em)
  set heading(numbering: none)
  show heading: set block(above: 1.4em, below: 0.7em)
  show heading.where(level: 1): set text(size: 22pt)
  show heading.where(level: 2): set text(size: 16pt)
  show heading.where(level: 3): set text(size: 12.5pt)
  show link: it => {
    if type(it.dest) == str { text(fill: rgb("#1565c0"), it) } else { text(fill: rgb("#2e7d32"), it) }
  }

  // Code
  show raw: set text(font: ("DejaVu Sans Mono",), size: 0.9em)
  show raw.where(block: false): box.with(fill: luma(240), inset: (x: 2pt), outset: (y: 2pt), radius: 2pt)
  show raw.where(block: true): block.with(
    fill: luma(246), stroke: 0.5pt + luma(210), inset: 8pt, radius: 3pt, width: 100%,
  )

  lesson-pagebreak.update(lesson-pagebreak-on)

  // Title page and contents
  page(numbering: none, align(center + horizon)[
    #text(28pt, weight: "bold", title)
    #v(1em)
    #text(12pt)[Based on the lessons at #link("https://www.learncpp.com/")[learncpp.com]]
  ])
  outline(depth: 2, indent: auto)
  pagebreak()

  body
}

#let chapter(label, title) = {
  pagebreak(weak: true)
  heading(level: 1, if label != "" [#label: #title] else [#title])
  after-chapter.update(true)
}

// The label lets other lessons link here: #link(<lesson-SLUG>)[...].
#let lesson-title(number, title, slug) = {
  context if lesson-pagebreak.get() and not after-chapter.get() { pagebreak(weak: true) }
  after-chapter.update(false)
  [#heading(level: 2, if number != none [#number #sym.dash.em #title] else [#title])#label("lesson-" + slug)]
}

#let callout(kind: "note", title: auto, body) = {
  let style = palette.at(kind, default: palette.note)
  let title = if title == auto { style.title } else { title }
  block(
    width: 100%, breakable: true, inset: (x: 10pt, y: 8pt), radius: 3pt,
    fill: style.color.lighten(90%), stroke: (left: 3pt + style.color),
  )[
    #if title != none { text(weight: "bold", fill: style.color, title); parbreak() }
    #body
  ]
}

// Images keep their natural size unless that's wider than the text column.
#let lc-image(path, width: auto) = layout(size => {
  let img = image(path, width: width)
  if measure(img).width > size.width { image(path, width: 100%) } else { img }
})

#let missing-image(label) = box(
  stroke: 0.5pt + gray, inset: 4pt, text(size: 0.85em, fill: gray)[image not downloaded: #label],
)

#let lc-table(..args) = align(center, table(
  stroke: 0.5pt + luma(180), inset: 5pt, align: left,
  ..args,
))

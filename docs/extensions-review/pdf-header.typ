// Pandoc/Skylighting token colors remain intact; zero-width break opportunities
// are a PDF-only layout operation, never a change to the source or EPUB bytes.
#show raw.where(block: false): it => text(
  font: "DejaVu Sans Mono", size: 8.4pt, hyphenate: false,
  it.text.clusters().join("\u{200b}"),
)
#let Skylighting(fill: none, number: false, start: 1, sourcelines) = {
  set text(font: "DejaVu Sans Mono", size: 8.4pt, hyphenate: false)
  set par(leading: .38em, spacing: 0pt, justify: false)
  block(width: 100%, breakable: true, fill: rgb("#f1f5f8"),
    inset: (x: 9pt, y: 8pt), radius: 3pt,
    above: 9pt, below: 10pt)[
    #for (index, ln) in sourcelines.enumerate() {
      grid(columns: (34pt, 1fr), column-gutter: 6pt, align: (right, left),
        block(inset: (y: 1.4pt), text(size: 7pt, fill: rgb("#66788a"), str(start + index))),
        block(above: 0pt, below: 0pt, inset: (y: 1.4pt), breakable: true,
          if ln == [] { [#v(8pt)] } else { ln }))
    }
  ]
}
#show raw.where(block: true): it => block(
  width: 100%, breakable: true, fill: rgb("#f1f5f8"), inset: 9pt,
  text(font: "DejaVu Sans Mono", size: 8.4pt, hyphenate: false,
    it.text.clusters().join("\u{200b}")),
)
#show heading.where(level: 1): it => {
  pagebreak(weak: true)
  set text(fill: rgb("#163e59"))
  it
}
#show heading.where(level: 2): set text(fill: rgb("#163e59"))
#show heading.where(level: 3): set text(fill: rgb("#163e59"))
#show figure.where(kind: table): set block(breakable: true)
#show table: set text(size: 8.5pt)
#show table.cell: set align(left)
#show table.cell: set par(justify: false)
#set table(inset: 5pt, stroke: .4pt + rgb("#c4d1da"),
  fill: (x, y) => if y == 0 { rgb("#e7eff4") } else { none })
#set page(margin: (left: 18mm, right: 18mm, top: 19mm, bottom: 19mm))

# Fable C2: JDK 17 `Locale.ROOT` lowercase oracle

Direct oracle for `String.toLowerCase(Locale.ROOT)` on Oracle JDK 17.0.8, the
JVM behind Spark 4.2.1's `CaseInsensitiveMap` column lookup, and the data from
which Sail's `sail_common::utils::root_lowercase::spark_root_lowercase`
(Sail `2dcd0eaa9`, correcting `f4537586b`) is generated and tested. No Spark
class is involved. `provenance.json` records the JDK, commands and hashes;
`jdk/` holds the probes, their raw outputs, the generators and the designed
strings.

## History

The first version (Sail `f4537586b`) modelled the JDK's final-sigma word
boundaries from single-neighbour probes (`RootLowercaseProbe.java`,
`generate_tables.py`, both retained). Codex's independent review
(`../fable-c2-context-review`, Grust `d401475b`) found 1,332 mismatches in
39,215 generated strings: a mark or format character after a digit belongs
to the number, so a following connector and sigma start a new word, which
per-code-point classes never composed. The model was replaced by a port of
the JDK's own break iterator.

## What the port is built from

- **Word-break tables.** `WordBreakTablesDump.java` reads, by reflection,
  the compiled tables of `BreakIterator.getWordInstance(Locale.ROOT)`
  (`sun.text.RuleBasedBreakIterator`, rule-data checksum `e227e00a`): the
  forward and backward state tables (22 categories, 20 and 15 states), end
  and lookahead flags, the category of every code point (2,076 ranges) and
  the code points `ConditionalSpecialCasing.isCased` accepts (137 ranges, from
  `Character.getType`). `generate_break_tables.py` turns them into Sail's
  `root_lowercase_tables.rs`, retained here byte for byte.
- **Algorithm.** Sail ports `isFinalCased` and the iterator's `isBoundary`,
  `following`, `handleNext`, `handlePrevious` and code-point stepping over
  UTF-16 units, including the lookahead rule, the resynchronisation after
  `handlePrevious`, the last-known-break cache across calls, a fresh iterator
  per sigma, and `CharacterIterator.DONE` (U+FFFF) ending a scan.
- **Scalars.** ICU simple lowercase gated to Unicode 13, with `İ` expanded;
  proven by the exhaustive FNV-1a hash in `probe.json`.

## Oracles the Sail tests replay

| Set | Size | Form |
| --- | ---: | --- |
| every Unicode scalar | 1,112,064 | hash |
| designed strings (`designed-all2.txt`) | 201 | explicit outputs |
| reviewed counterexamples | 13 | explicit UTF-16 outputs |
| review enumeration (7 symbols, suffix length 0–5, two frames) | 39,215 | regenerated in the test, hash |
| seeded xorshift64* strings, 62-code-point alphabet, length 1–8 | 40,000 | regenerated in the test, hash |

All five match. Codex's independent corrected-review corpus (68,588 strings, `../fable-c2-corrected-review`) also replays with zero mismatches through the opt-in test added in Sail `d38058973`; the independent lookup corpus (16,684 queries) replays through the opt-in test in Sail `1eea0b140`. The enumeration reproduces the review's set exactly (same
count). Context parity beyond these sets is not claimed; the port is exact
by construction only to the extent the dumped tables and the ported
algorithm are, which the random set is designed to exercise.

# Fable C2: JDK 17 `Locale.ROOT` lowercase oracle

Direct oracle for `String.toLowerCase(Locale.ROOT)` on Oracle JDK 17.0.8, the
JVM behind Spark 4.2.1's `CaseInsensitiveMap` column lookup, and the data from
which Sail's `sail_common::utils::root_lowercase::spark_root_lowercase`
(Sail `f4537586b`) is generated and tested. No Spark class is involved; this is
JDK string behavior only. `provenance.json` records the JDK, commands and
hashes; `jdk/` holds the probe, its raw outputs, the generator and the designed
strings.

## What the probe observes

- **Exhaustive scalar hash.** For every Unicode scalar, the JVM lowercase of the
  one-character string, UTF-8, followed by a zero byte, folded into 64-bit
  FNV-1a. The Rust test recomputes it; equality proves single-code-point parity
  for all 1,112,064 scalars, including `İ` (two code points) and a lone `Σ`.
- **Simple mapping table** (`Character.toLowerCase`, 1,393 entries) retained
  for reference; the Rust port derives the same mappings from ICU's simple
  lowercase gated to Unicode 13 and proves it by the hash above, so no table is
  embedded for scalars.
- **Final-sigma neighbour classes.** `ConditionalSpecialCasing.isFinalCased`
  uses the JDK's own word `BreakIterator`, not UAX #29 or case-ignorable
  skipping. Each class is observed one code point at a time with a fixed
  frame: cased-after (`ΑΣX`), cased-before (`XΣ`), word-after (`ΑΣXΑ`),
  word-before (`ΑXΣ`), letter connectors (word-after but doubled breaks),
  number connectors (`ΑΣ1X1Α`), and the four neighbour classes a connector
  needs on each side (`ΑΣX-Α`, `ΑΣ-XΑ`, `ΑΣX.5Α`, `ΑΣ1.XΑ`). The generator
  turns them into the range tables in Sail's `root_lowercase_tables.rs`.
- **Designed strings** (201): sigma between letters, digits, marks, format
  characters, every connector singly and doubled, mixed letter/digit frames,
  supplementary letters (Deseret, Vithkuqi, Georgian Mtavruli, Cyrillic TJE),
  dotted and dotless I, expansions, whitespace and line separators. The Rust
  test asserts every one; the Python simulation in the generator reports zero
  mismatches on this set.

## Boundary of the claim

Single-code-point parity is exhaustive. Sigma context parity is proven on the
designed set only: the connector rule ("inside a word only between two letters,
or a number connector between two digits") is a model of the JDK's legacy word
rules derived from single-neighbour probes, and longer punctuation sequences
outside the designed set are not claimed. The model and its acceptance set are
retained here so any counterexample can be added to `designed-all2.txt`, rerun,
and either fixed or recorded as a divergence.

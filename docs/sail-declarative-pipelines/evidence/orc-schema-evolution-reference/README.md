# ORC requested-schema evolution reference

Two fresh Spark 4.2.1 runs add 32 retained observations: 28 evolution/inference
cases (25 successes and three errors), then four successful nested-name cases.
This packet is a Spark baseline, not a Sail runtime or full SDP test verdict.

- [Evolution and inference](evolution/README.md): requested TIME precisions and
  interval qualifiers preserve stored values; integer narrowing nulls overflow
  under ANSI true; mixed and missing names; eleventh-file semantic schema merging;
  and `_col*` positional fallback.
- [Nested name follow-up](nested-matching/README.md): for the tested ASCII names,
  case-insensitive matching chooses the last normalized physical field, even
  when an earlier field has the exact requested spelling. This differs from
  Spark's top-level ambiguity check. Installed ORC class disassembly supports
  the observation; it is not loaded-class instrumentation or a Unicode guarantee.

The next adapter must keep read-schema interpretation distinct from SQL casts.
TIME precision and interval qualifier changes do not invoke SQL truncation.
Safe narrowing returns null on overflow. Semantic schema merging must compare
TIME precision and union qualifiers within the same interval family; equal
Arrow storage alone cannot establish type equality. All-file inference must see
file 11. Preserve full-schema timestamp checks before projection from the prior
checkpoint. Nested case handling must not inherit an unqualified recursive
ambiguity rejection rule.

The experiments record configurations, requested/read/output schemas, exact
values, errors, pre-execution formatted plans and immutable fixture hashes.
TIME is explicitly enabled after recording its disabled default. Both owned
JVMs exited normally. Limits and reproduction instructions are in each packet.

The installed ORC 2.3.0 class bytes are accompanied by the release's LICENSE and
NOTICE under `orc-java-license`; their provenance records the immutable Apache
ORC release commit. No Oracle JDK implementation classes or sources are included.

# Independent review of the corrected C2 iterator

Sail `2dcd0eaa9` replaces the single-neighbour sigma model with a table-driven
JDK17 word-break iterator port. The exact offered helper and tables were compiled
in independent minimal crates, using the same top-level locked ICU/regex versions.
No production source or Fable worktree was modified.

The corrected helper matches fresh Oracle JDK17.0.8 ROOT lowercase on all
**68,588 strings**. The first 39,215 inputs are byte-for-byte the earlier
[counterexample corpus](../fable-c2-context-review/README.md); the correction fixes
all 1,332 previously observed mismatches. The new set adds 30,000 seeded context
draws and 1,000 arbitrary Unicode draws, with sigma inserted, then deduplicates.
It covers longer mark/connector sequences, controls, U+FFFE/U+FFFF, supplementary
characters and assigned/unassigned scalars. The valid UTF-8 input domain excludes
lone Java surrogate units. The recorded outputs contain every passing comparison.

The combined lookup/helper source at the corrected head also matches fresh Spark
StructType results on all **23,050 queries across 771 schemas**, replaying the
[independent C4 corpus](../fable-c4-independent-review/README.md). The stored
6,366 offered expectations match the fresh JVM too. Classpath hashes match the
prior pinned Spark4.2.1/Scala2.13.18 oracle. The kernel is unchanged; the earlier
16-test kernel gate remains tied to its exact source objects.

The former C2 behavioural blocker is resolved on these independently tested
corpora. The correction can proceed to combined integration review, with the
remaining C5 phase and C6 evidence/wire changes and exact combined gate still
required. Finite helper corpora do not establish all possible string contexts or
public CDC reachability. Full Sail/Grust library, public runtime and original SDP
suite verdicts must not be inferred from these minimal-crate probes.

Both subdirectories preserve exact sources, Cargo locks, input cases, raw outputs,
commands, tool/binary hashes and historical harnesses. The lookup probe also
retains its exact hex input protocol. Harnesses expect fresh absolute output
directories. `provenance.json` hashes every packet file except itself.

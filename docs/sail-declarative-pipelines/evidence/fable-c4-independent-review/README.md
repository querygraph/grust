# Independent C4 kernel and lookup review

Reviewed Sail `a495cb02d` and Grust `727baa3e983a6a8b1d6055f8c3b0ccdb85bd78b3`.
The generic kernel delegates index lookup to the engine. Sail retains first
insertion positions while updating exact duplicate indices, uses the small-map
threshold on distinct exact spellings, and traverses improved Java UTF-16 hashes
with direct payloads before child buckets and insertion-ordered full collisions.
The new schema call site supplies this resolver to the kernel.

## Observed checks

The exact offered lookup/helper/table sources were compiled in an isolated Rust
crate with the locked top-level ICU/regex versions. The harness supplies only the
two-variant Case enum and a hex-line input/output driver; it does not build the
whole Sail service. A fresh JVM calls Spark StructType directly.

All **23,050 queries across 771 schemas match** for both exact and insensitive
indices. That includes replaying Fable's 515 schemas / 6,366 queries, whose stored
expectations also match the fresh JVM, plus 256 newly generated schemas / 16,684
queries using seed 20261030. The fresh set includes duplicate names, case variants,
empty names, supplementary characters, and families of true Java string hash
collisions constructed from Aa/BB. Every input and both raw outputs are retained.
All JVM classpath hashes match the earlier pinned Spark4.2.1/Scala2.13.18 oracle.

All four vendored kernel files byte-match their Grust source objects and
SOURCE.json hashes. The exact standalone kernel passes **16 tests**, strict
Clippy (including explicit unwrap/expect/panic denial) and formatting. This is a
focused kernel gate, not a full Grust workspace or combined Sail verdict.

## Acceptance boundary

The resolver refactor and the reviewed map-order mechanism are accepted at this
source/component scope. C4 remains unintegrated pending the C2 lowercase correction,
C5 phase fixes and the exact combined integration gate. The generated map-order
set does not cover arbitrary Unicode contexts; the known
[C2 counterexamples](../fable-c2-context-review/README.md) still stand. These direct
StructType probes do not establish public CDC reachability or execution parity.
No Fable worktree or offered history was changed.

The first independent driver failed to compile because its generated Rust char
literal contained a raw tab. The harness now emits an escaped tab. The failed
harness/log are retained; offered sources were unchanged and no comparison result
from that failed run is counted. Historical harnesses use absolute paths and fresh
output directories. Cargo locks, source files, commands, tool/binary hashes and raw
logs are retained. provenance.json hashes every packet file except itself.

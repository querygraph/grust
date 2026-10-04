# PageRank emission cursor: last lease versus sequence storage

The unchanged Sail `a3462345a6764096024c055dc4d105a3c634e5a4` cursor releases
its last host memory lease before deallocating its sequence vector in the
last-owner, abandoned-cursor case. The lease callback observes one tracked
2,056-byte allocation still live even though native admitted bytes are zero.
The eventual sequence deallocation occurs exactly once.

The [baseline receipt](baseline/receipt.json) records two passing controls and
one expected failure. A retained contribution keeps its ownership lease after
cursor destruction; a completed `Emission` owns the sequence vector and drops
that vector before its ownership guard. Both are positive controls and pass on
the unchanged source.

The [candidate patch](candidate.patch) moves only the cursor's `sequences`
field declaration before `ownership` and `resources`, plus a comment and the
same standalone test module. Rust drops struct fields in declaration order
after the cursor's existing cancellation destructor. No arithmetic, emission
ordering, cancellation behavior or public signature changes. The
[candidate receipt](candidate/receipt.json) records all three tests passing.

The test uses 257 partitions and three local vertices owned by partition zero.
Tracking starts immediately before `start_emission`, after graph and inbox
construction. Exactly one allocation must match `257 * size_of::<u64>()`; its
pointer is tracked until deallocation. Preexisting same-size buffers are not
counted, and a second matching allocation fails the test. The partition and
external `Resources` owner are absent before the cursor's final drop. The
lease callback records actual allocation liveness separately from admission.
The test uses no deadline, sleep, thread race or RSS measurement.

Both runs use isolated detached checkouts at `a3462345`, a private APFS cloned
core target, offline release compilation, two build jobs, and one test thread.
The baseline staged tree is `bc41f04b487bab476894ec53183c58ed52fa57e2` with
only the added test; the candidate tree is
`c9e320999b34f764dd96a55daef698154a476cbb`. Rust is 1.97.1
(`8bab26f4f68e0e26f0bb7960be334d5b520ea452`, aarch64-apple-darwin).

`run_control-baseline.py` preserves the exact first driver. The current driver
adds an explicit detached-HEAD assertion before the candidate run; the test
source and behavioral assertions are identical. Original logs and failed
baseline remain unchanged. No production commit, push, remote workload or
Native agent target mutation was performed.

This proves the narrow last-owner lifetime defect and its field-order fix.
It does not measure RSS, elapsed performance, total memory savings, other
cursor types, or the cause of earlier stream failures. An external lease alias
can delay release and mask this ordering, as the contribution control shows.
The expanded Argentea component must integrate and gate this patch separately.

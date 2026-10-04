# Argentea raw-input lifetime

Repository `querygraph/sail`, branch `work/argentea-owned-input`, commit
`7f5b80d0fe35cf8520f80078ee0dbd50b1a5833d`, directly atop
`200d1cf8eb1db5e9057e09e071ebd57391f4b376`. The branch and detached gate are clean.
This change is committed locally and **not pushed**.

BFS and SSSP now expose an opaque preparation that owns the validated CSR.
The existing `build` API remains `prepare(...).finish()`. Nutmeg prepares the
CSR, drops raw vertex and edge vectors, releases their `MemoryAccount`, then
allocates labels/frontier and initial protocol state. CSR algorithms, endpoint
validation, float order, protocol code and host Rust are unchanged.

The prepared object owns its original operation, options and resources; it
cannot be cloned or finished twice. Its field order drops CSR storage and
admission before the host lease, including when the sole owner abandons it.
The final implementation and source-only independent review are pinned in
[the final receipt](final-receipt.json) and
[independent audit](independent-source-audit.json).

## Measured boundary

These are per-partition requested heap peaks measured by a thread-local System
allocator counter on Capitola, a 64-bit macOS host. Raw-vector construction is
included so freeing raw input cannot subtract unmeasured bytes. Each row has
65,536 local vertices, a fixed three-partition operation and the indicated arcs
per vertex. This is an allocation experiment, not an RSS or timing measurement.

| Algorithm | Arcs/vertex | Original peak bytes | Candidate peak bytes | Reduction bytes |
|---|---:|---:|---:|---:|
| BFS | 0 | 4,195,240 | 3,670,952 | 524,288 |
| SSSP | 0 | 4,195,248 | 3,670,960 | 524,288 |
| BFS | 1 | 5,768,104 | 4,195,240 | 1,572,864 |
| SSSP | 1 | 6,816,688 | 4,719,536 | 2,097,152 |
| BFS | 8 | 16,778,152 | 14,156,032 | 2,622,120 |
| SSSP | 8 | 25,166,768 | 22,544,568 | 2,622,200 |

All 12 matched shapes (1,024/65,536 vertices, 0/1/8 arcs, BFS/SSSP) retain the
same allocation count, total allocated bytes, metered work and final admitted
storage. The exact ordinary and saturated runs reproduce all counters. The
unchanged `200d1cf8` production probe matches the candidate's retained-input
control exactly: [matched counters](matched-final-counters.json),
[baseline provenance](baseline-source-receipt.json), and
[baseline probe](baseline-probe.rs).

Conservative CSR-build admission still overlaps raw inputs. Its peak is
unchanged for the arc-bearing fixtures; the isolate fixtures reduce admitted
peak only by fixed state metadata (1,064 BFS / 1,088 SSSP bytes). Raw/CSR overlap,
input Arrow buffers, repeated input-vector growth, the copied vertex vector,
and active-round label copies remain. No speed or cluster improvement is
claimed. Reusing vertex capacity requires explicit capacity/admission transfer
and is outside this change.

## Validation and retained failures

[Exact gate](exact-gate/receipt.json):
`ARGENTEA_INPUT_LIFETIME_GATE PASS 7f5b80d0fe35cf8520f80078ee0dbd50b1a5833d exact commit`.
It ran full core formatting, strict all-targets core clippy, formatting of the
four changed/new native implementation/test files, **120 core tests and 51
native tests** (45 Argentea adapter tests), then repeated both test suites with
every local core saturated. All load children were reaped. Own isolated targets,
`CARGO_INCREMENTAL=0`, disk checks, source hashes and branch/detached HEAD guards
are in the receipt. Inherited full-native formatting exceptions are explicitly
excluded; parent test files only gain module declarations.

- Core differentials cover all three BFS and both SSSP algorithms, signed ID
  extremes, empty owners, directed/undirected BFS, duplicate arcs, isolates,
  weighted ties/signed zero, exact float bits, independent oracles and protocol
  traces. Validation errors, cancellation, admission failure, abandoned
  preparation and sole-owner lease release have separate controls.
- Real local Nutmeg adapter controls retain a blocker through initialization,
  leaving exactly CSR-build headroom for 1,024/65,536 isolates. Both controls
  fail against unchanged baseline with memory-budget errors
  ([baseline receipt](baseline-native-control/receipt.json),
  [failure output](baseline-native-control/stderr)); both pass after the split
  ([candidate receipt](candidate-native-control/receipt.json)), and in full
  exact gates. They do not represent a distributed worker/Flight execution.
- Independent review caught an introduced preparation field-order bug before
  commit. The last-owner callback observed 28,680 admitted bytes when its host
  lease was released. The failing regression and source are retained in
  [the pre-fix log](last-owner-before-fix.log) and
  [pre-fix patch](last-owner-before-fix.patch). Moving CSR before Resources fixes
  abandonment; the final callback also covers cancelled finish for BFS/SSSP.
- The first formal runner mistakenly demanded native test inventory from its
  formatting step, although formatting passed. Its
  [failed receipt](candidate-gate/receipt.json) and
  [runner source](run_gate-attempt01.py) remain. The corrected runner gates the
  inventory only on test steps; [candidate gate 02](candidate-gate02/receipt.json)
  passed without a Sail source change.
- Initial final-counter parsing omitted two complete records prefixed by Rust
  test status. [The parser failure](postprocess-attempt01-error.json) remains.
  [The corrected parser](finalize.py) requires all 24 unique complete records
  per exact log and exact equality; raw logs and assertions are retained.

The commit followed the successful detached gate, exact frozen-receipt/source
verification and `git commit` in one `&&` chain; the matching detached worktree
then checked out the commit without force and ran its exact gate. This is an
experimental fork change. There was no remote host operation, Linux rebuild,
stream-loss diagnosis, host runtime qualification or default promotion.

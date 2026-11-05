# Extension design checkpoint and optimized filter qualification

The full reimplementation goal remains active, including existing Extensions and
an additional C ABI route from Apache DataFusion Comet. The preceding foundation
increment remains at local source commit `2c9fa84994d317aade0d1c69faa9a378c780127d`.
This checkpoint changes design documents and records source research; it does not
claim a new production adapter. The optimized component comparison completed;
it remains a shared-host diagnostic rather than production qualification.

## Authoritative sources

`EXTENSIONS-RESEARCH.md` records exact existing-host, scalar-prototype, Comet and
Sedona pins, inspected hashes and primary links. Seven specialty reports review
the measurement method and cumulative design within their specialties. Source
inspection is distinct from execution throughout.

The corrected proposal and E1–E5 preserve the existing DataFusion-FFI path, require
explicit per-export admission, and separate Comet scalar integration from relation
design. The integration note adds the StreamSource, replay, memory and lifetime
dependencies. The top-level plan now carries Extensions explicitly. Earlier
proposal versions are retained here as evidence, not current requirements.

Comet’s pinned scalar ABI is not release-stable, supports immutable kernels and
requires a null reserved constant-argument pointer. Its importer relies on
process-retained code for callbacks in returned arrays. The Sail prototype needs
that ownership proof and argument-field metadata preservation before integration.
Existing host registration also needs code/session-state separation and explicit
purity admission rather than relying on comments. No external-library execution,
new Spark-engine run or source modification was performed for this checkpoint.

## Completed optimized comparison

The unchanged foundation commit was built with
`CARGO_PROFILE_TEST_OPT_LEVEL=3`, `CARGO_PROFILE_TEST_DEBUG=0`,
`CARGO_INCREMENTAL=0` and its own target directory. The existing runner uses
`--profile test`, so it retains the opt-level override. Both baseline and candidate
operators compile into the same probe. This differs from the workspace’s release
profile with link-time optimization.

The completed process was unified-exec session `29326`. Its local log is
`/Users/alexy/src/sail/tmp/streamsource-build-20261105-b52144955/review-logs/filter-cost-opt3.log`.
The immutable run directory is `review-logs/filter-cost/runs/20261105T231322.884712Z`
under that worktree. `optimized-probe-start.json` records the initial command,
environment, source pin and initial compiling state. The completed receipt in
`optimized-filter/receipt.json` supersedes that status. The source stayed unchanged,
Cargo reported an optimized build and the probe passed all twelve cells.

The probe validates exact ordered outputs before timing and retains all paired
samples locally. `optimized-filter/SUMMARY.md` preserves every cell as ratios.
Data-only medians were 0.9971–1.0082; alternating-marker medians were
30.5485–600.5340, with 65,536 output batches. End-of-run host load was high and
CPU steal was unmeasured. Do not interpret the difference from unoptimized ratios
as a measured optimization effect. No absolute production throughput is claimed.
The separate sparse/grouped probe also completed with exact output validation
on unchanged source. Eight input batches of 8192 rows selected half their data.
A tail marker produced 16 output batches and a 1.1766 median elapsed-time ratio;
two adjacent middle markers produced 24 batches and a 1.1838 ratio, against eight
baseline batches. All seven paired samples and source remain local under
`review-logs/filter-layout/`; `optimized-layouts/` contains the receipt, complete
ratio table and artifact hashes. These fixtures support a bounded batching
experiment; shared-host diagnostics do not qualify production performance.
Original unoptimized results, raw samples and failures remain retained.

## Next source increment

Qualify the standalone Comet scalar adapter with process-retained library code,
complete argument fields and declared pure immutable admission. Compare the pinned
importer/layout with the existing prototype under attribution rules. Add lifetime,
metadata and error counterexamples before package wiring. Independent SDK-built
producer evidence remains necessary for interoperability. Host/package integration
and C relations retain separate reviewable boundaries.

Distributed source control, checkpoint alignment, durable preparation, target
fencing, CDC merge, strict configuration/Dhall and migration remain requirements
of the full goal. Neither this checkpoint nor the foundation tests qualify them.

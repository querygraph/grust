# Extension design checkpoint and optimized filter qualification

The full reimplementation goal remains active, including existing Extensions and
an additional C ABI route from Apache DataFusion Comet. The preceding foundation
increment remains at local source commit `2c9fa84994d317aade0d1c69faa9a378c780127d`.
This checkpoint changes design documents and records source research; it does not
claim a new production adapter or a completed optimized benchmark.

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

## Active optimized comparison

The unchanged foundation commit is being built with
`CARGO_PROFILE_TEST_OPT_LEVEL=3`, `CARGO_PROFILE_TEST_DEBUG=0`,
`CARGO_INCREMENTAL=0` and its own target directory. The existing runner uses
`--profile test`, so it retains the opt-level override. Both baseline and candidate
operators compile into the same probe. This differs from the workspace’s release
profile with link-time optimization.

The live process is unified-exec session `29326`. Its local log is
`/Users/alexy/src/sail/tmp/streamsource-build-20261105-b52144955/review-logs/filter-cost-opt3.log`.
The immutable run directory is `review-logs/filter-cost/runs/20261105T231322.884712Z`
under that worktree. `optimized-probe-start.json` records the initial command,
environment, source pin and observed compiling state. Poll the actual process
before interpreting an older receipt as still active. No result is claimed here.

The probe validates exact ordered outputs for all twelve cells before timing and
retains all paired samples. After completion, inspect compiler optimization
evidence, source invariance, build completion, every result cell and shared-host
limitations before making a verdict. Then test sparse and grouped markers before
choosing a buffering policy. Keep the original unoptimized results and failures.

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

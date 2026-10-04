# Remaining gate work: source and evidence readiness

This directory records preparation, not new benchmark results. A2 and A3 are
complete in their sibling evidence directories. B8 is executing separately;
its final report will retain both datasets, both ABBA blocks and every outcome.
The resource correction in `../C3-NATIVE-QUOTA-CORRECTION.md` applies throughout.

| Item | Existing evidence | Work still needed |
| --- | --- | --- |
| C2 | Current runtime source and historical distributed task evidence | Bind operations to jobs and observe planning, encoding, scheduling, stream setup and release; then run the P4/16/32 cold/warm control. Current source cannot supply the complete breakdown. |
| C3 | A3 configured driver/worker pools total 30 GiB; sampled PSS, cgroup peaks and OOM outcomes are preserved | Actual pool/native reservations, transport bytes and spill accounting. Configured quotas are not observed allocations or a physical memory guarantee. |
| C4 | Compact tuple MIN passed its exact source gates, a Linux traversal pair and a separate large certificate | Linux standalone allocation probes and one current-runtime distributed `min_by` control. Historical standalone allocation figures were measured on macOS. |
| D2 | Exact declared-layout source is available at `17f8461f1cb042ea0375537cf8fa16c7ba6594eb` | A separately pinned host/wheel build, mandatory missing-bucket correctness control, and paired process-cluster measurements. This source predates the frozen typed Pecan runtime. |
| F2a | Current Banda sources and Sem's external receipts are identified | Preserve `asStaged`, full Parquet input/output, one and three calls on the same revision, explicit memory admission and correctly observed read/build/kernel/write boundaries. Lazy `run()` time is not kernel time. |
| X1/X2 | Historical failures and later logging controls remain distinct | Supervised reproductions with first-fault evidence, actual source/runtime parity, full output checks and confirmed process closure. Later OOMs or successful compact runs do not explain earlier losses without OOM. |

The accompanying plans and JSON audits preserve source identities and the limits
of each claim. Absolute paths identify the original local evidence; source commits
and file hashes provide portable identities. No new engine qualification follows
from a source review alone.

## Specific findings to keep in the controls

- Declared-layout's distributed writer can leave empty hash buckets without files.
  The reader requires all buckets, and the client catches a missing-bucket error
  as an empty graph. This is a source-derived concern, not a reproduced mismatch.
  Test a nonempty graph with fewer keys than partitions before timing it.
- Current randomized Pecan WCC uses grouped MIN and `least`; the earlier fused
  `min_by` expression is no longer its implementation. Standalone tuple MIN and
  ordered LAST / `min_by` are different result contracts.
- Banda's result relation is lazy. Projection construction, the kernel, Arrow
  conversion and writer backpressure can occur within the eventual write action.
  Retain overlapping phase spans or explicit materialization boundaries; do not
  subtract diagnostic durations and present the remainder as a kernel measurement.
- Banda retains normalized staged Arrow rows alongside its projection and CSR.
  The corrected edge-record layout is inferred as 40 bytes and still needs a
  target layout check. The [retention audit](F2a/STAGED-RETENTION.md) records the
  additional buffers, ownership and memory admission limits.
- The signed-isolate WCC mismatch retained in A2 remains unresolved at the frozen
  source. Correct shape controls or cit-Patents results do not qualify generic WCC.

Preparation does not change the frozen A2/A3/B8 controller, runtime, native package,
input files, oracles, measured cells or their timer boundaries.

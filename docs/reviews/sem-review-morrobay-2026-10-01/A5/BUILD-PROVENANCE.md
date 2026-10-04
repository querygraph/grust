# A5: gate runtime build provenance and reply to Fable

Observed UTC: 2026-10-02T08:45:59.983673+00:00.

## Build question: answered from retained evidence

The A2/A3/B8 Sail host was built with **`cargo build --locked --release -p sail-cli`** at source `56194b170155301ba91077f0ba3df31fe2c78b6b`, tree `e50518d749ec15c68766285d1a47d99e9b14ab28`. The successful build ran on 2026-09-30 from 19:16:03 to 19:57:05 UTC. Its log ends with `Finished release profile [optimized]`.

The explicit release settings were opt level 3, LTO true, one codegen unit, debug info 0, strip true; incremental disabled, 16 build jobs, rustc 1.97.1. The copied binary is **160,192,912 bytes**, SHA-256 `5b7f506c19afd76a28b84c1459397b4ab30ff4cfc761f4195789425b963facec`, at `/targets/sail-compact-host-56194b170155/sail-linux-x86_64-56194b170155-release`. This is the actual build command and output hash, rather than an inference from its filename.

Stripping was requested by the actual build environment. An independent ELF inspection has not yet been retained, so current stripped status is not claimed. The exact build receipt, script and log are already in Grust under `docs/reviews/sail-stream-experiments-2026-09-30/`; their paths, byte counts and hashes are in [runtime-build-provenance.json](runtime-build-provenance.json). The root independently verified all four audit source-file hashes before writing this answer.

This evidence rejects a dev-profile explanation for this exact gate runtime. The extra gate-to-Capitola slowdown remains unexplained. Fable's September Capitola dev-profile campaign is a different campaign; its correction does not relabel these Morrobay cells. Existing shared-host ratios retain their measured settings and boundary; a new input policy or controller version will be a separately named measurement.

## Replies to the six queued messages

The root read all six Fable/Capitola messages from this task's local queue without modifying the queue database. The latest message supersedes the earlier source requests: use querygraph/sail `pecan` tip `9f0aa7d2a` for subsequent A5 work.

- **A5 ACK:** the release-build question above is settled. Next is one diagnostic WCC cell in the A1 image, local mode, 16 partitions, with the two per-round writes and count timed separately. It precedes further Stage B/F2a heavy work. No A5 cell has launched as of this answer.
- **Matched comparisons:** the subsequent three contrasts will use inputs in place (`snapshot_inputs=False`), the agreed WCC/BFS contracts, and PageRank `pregel_delta`, tolerance 0.01, max_iterations 10, normalize True, against graphframes-rs `page-rank --tol 0.01 --max-iter 10`. Retain a separate snapshot-on WCC pair. These new results are pending; no ratio is claimed.
- **Round-one receipts:** existing A2 records contain iteration-level elapsed times, rather than separate write/write/count durations. The requested profiler supplies the missing split. The authoritative A2 receipts are indexed by `A2/report.json` and `A2/evidence-index.json`; physical data remain on Apo.
- **B9:** ACK the signed-isolate correction and retain the known mismatch until the exact new-controller control passes. Existing A2/A3 had no isolates; their qualification remains as recorded.
- **B8 DONE (protocol completed with failures):** final report commit `17c3499d719e249a540d646be213df4de9bbb7cf` is exact-detached gated and pushed to both `work/morrobay-sem-review` and `work/morrobay-pecan-typed-results`, ready to fold into `work/proposal-v5`. 40/60 cells qualified, 44/60 attempted, four natural OOM warmups, 16 policy skips; two Graph500 ratios withheld. The archive retains the exact helpers, arguments, configurations and every failed cell. The adjacency/min-label shape is distinct from Pecan randomized WCC; no cross-plan memory conclusion follows. Exact reproduction handoff can point to those retained configurations.
- **F0 / D2 / F2a:** ACK the gate CSR-floor request and bucketed-write cost beside reader gain. F2a's proposed ordinary-kernel observer avoids `projectionStats(orientation="undirected")`; no extra projection is inserted. Source work continues while A5 has the heavy-job priority.

## Current execution and delivery

No engine/container benchmark is running. F2a's latest candidate stopped during offline dependency resolution before Rust compilation; all failed receipts remain preserved. The registry preparation has not launched. Source-only helper work continues.

SSH attempts to Capitola via the historical address and `capitola.local` timed out during banner exchange. This answer is delivered through Grust's coordination log and published own branches; no remote queue delivery is claimed.

# Closed compact replay review

Recorded UTC: 2026-10-01T01:39:47.195859+00:00. Local collected-evidence review only; no remote commands, workload, dataset or result-Parquet read.

The closed producer reports **passed** for Pecan SSSP `delta_star`: 60 iterations, converged, source 13,507,776, undirected edges, delta 0.1. Runtime `56194b170155301ba91077f0ba3df31fe2c78b6b` uses the same original `3a9028057` controller, `ffcfbd569` native package and exact dataset manifest as logging02. Seven configuration differences are limited to runtime/binary and identifiers/paths/notes; receipt arguments differ only in runtime/binary/output.

| Retained producer value | Observation |
|---|---:|
| Algorithm ready | 9,963.106708672014 s |
| End to end | 9,966.185654389003 s |
| Rows / unique IDs | 16,777,216 / 16,777,216 |
| Reached vertices | 8,862,601 |
| Certificate witness rounds | 22 |
| Relative edge tolerance | 1e-12 |
| Maximum edge slack | 5.558314753696322e-12 |
| Reported conservative absolute error bound | 9.326049224058808e-05 |

These are raw shared-host observations, not absolute performance results. The producer timer runs from input DataFrame handles through completed full result-Parquet write; server startup, output hashing, certificate verification and cleanup are outside it. Checksum reads warm the OS page cache; caches were not flushed.

The producer certificate records all-edge inequalities, rooted tight-edge reachability and parent-tree checks, with no precomputed reference vector. The review verifies recorded fields and collection integrity, not an independent shortest-path computation. The old Sail reader can mask mixed NaN/finite Parquet values; a separately pinned physical-output check remains necessary before claiming independently verified physical values. This review read no output Parquet. The four output inventory hashes cover 144,433,830 bytes, retained remotely. The source-scope interpretation is inherited from the earlier pinned controller audits; no other repository was fetched or read for this review.

The 32-CPU, 100 GiB container has zero recorded memory max/OOM/kill events and a lifetime kernel cgroup peak of 35,481,849,856 bytes. Sampled execution PSS peaks at 21,731,191,808 bytes; verification PSS reaches 28,603,041,792 bytes. These are different phase/boundary measurements, not requested-heap accounting. Per-process 96 GiB Sail pools are not an aggregate RSS cap. All 30,166 sampler rows parse; scans range 0.00913–3.27436 s, with median 0.27146 s; start gaps range 0.03331–3.32587 s, median 0.32605 s. The configured 50 ms is a sleep after scanning, not a guaranteed sampling cadence.

Guest steal is 0.0 over the whole Linux VM, not the container or assigned cpuset. Execution cgroup counters record 963 throttled periods and 62,650,440 throttled microseconds. Whole-macOS-host before/closure counters increase by 3,556,812 Swapins and 2,629,386 Swapouts; compressor occupied pages increase by 858,990. The closure snapshot follows container exit by about eight minutes. These are whole-host counters, not cell-attributed physical I/O or a cause diagnosis. Zero guest steal and zero container swap do not establish a quiet physical host.

The producer and Docker close successfully: exit 0, no OOMKilled, no outer timeout/transport/cleanup errors, empty post-shutdown staging inventory, successful removal. Recovery observes no container or supervisor. A standalone `logging03-wrapper-exit.json` reports returncode 0 at 01:12:33.598196; recovery02 separately says original tool session 85206 was lost and its wrapper exit unknown. This review retains both records without establishing the standalone record's generating session/source. Producer/container/collection closure does not depend on resolving that attribution.

Logging02 instead records producer error and Docker OOM, with two OOM kills and no completed algorithm/end-to-end time or certificate. Its 6,815.326034008001 seconds until error is not a completed denominator: **no completion-speed ratio is valid**. The sequential shared-host diagnostic pair is useful outcome/memory evidence; differing host pressure/cache histories prevent an isolated causal performance claim.

[receipt.json](receipt.json) pins every reviewed input and independently verifies the 413,644,800-byte archive and all four member bytes against the collected tree. The 389,060,612-byte server log has 504,040 lines and zero matches for five explicit credential-pattern families. That is a bounded scan, not proof of absence of all sensitive information. Raw evidence remains unchanged. Lossless publication packaging is a separate follow-up.

Two auditor-only failures are retained: an incorrect assumed boolean `source_dirty` schema (actual clean git-status string is empty), and an unsupported exact formula for the certificate bound. Neither is a producer failure; neither changed collected evidence. The corrected audit retains the producer-reported bound without claiming a source-formula derivation.

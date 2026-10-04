# Native execution and graph VM retirement completed

Observed UTC: 2026-10-02T10:18:37.388557+00:00.

Alexy's instruction is the execution contract: run graph benchmarks on bare macOS and use a VM for Linux build testing. The graph VM profile `sail-gate` and its data disk were deleted. Historical A2/A3/B8 records retain their original execution class.

## Optimized native binaries

Both exact detached builds completed with `cargo build --locked --release`, rustc 1.97.1, optimization 3, LTO enabled, one codegen unit, debug 0, stripping enabled and incremental disabled. Both binaries are x86_64 Mach-O executables and their startup probes returned 0. Source commit/tree, manifest and lockfile identities agree before and after each build.

| Binary | Source commit | Bytes | SHA256 |
| --- | --- | ---: | --- |
| Sail | `9f0aa7d2a50f1258544d37c05dd19b3ff3d915b3` | 150,472,188 | `ee80ac3cf9d028639561f3cf32435985192719d629807fcf6a368324fa84946e` |
| graphframes-rs | `b4da56dabe20bba8e29563e06acc5179b2113ce3` | 72,311,876 | `41780fcebd40c420281f1b2ac0df15ed19679d06f917faacfe2f1402db15a952` |

Build artifacts are under `/Volumes/Apo/graph-tests/results/sem-review-20261001/native-optimized-build01/{sail-target,graphframes-target}/release/`. The [build receipt](native-build-receipt.json) records exact commands, environment, architecture, probes and source closure. Combined completion: 2026-10-02T10:10:25.435124+00:00.

## VM deletion and retained experiment data

The [retirement receipt](vm-retirement-receipt.json) records successful deletion at 2026-10-02T09:42:42.354851+00:00 after a complete portable archive audit. Main-volume free space increased from 129.1 GiB immediately before retirement to 292.2 GiB afterward. That before value follows an earlier VM compaction; it is a separate observation from the initial approximately 43 GiB free. The publishing profile `default` configuration hash was verified across this graph-profile deletion.

The portable archive contains inputs, final results, logs, receipts and source; compiled targets, dependency environments and transient staging are excluded. No VM disk image is retained.

- Archive: `/Volumes/Apo/graph-tests/results/sem-review-20261001/graph-vm-retirement01/experiment-data.tar.zst`, 47,585,750,817 bytes, SHA256 `74dd0ed48eef231fbf30ec08fb56787b52d81b04604b3dfcb5540d333245671b`.
- Every regular member was decoded and hashed: 163,893 files, 66,062,556,202 uncompressed regular-file bytes.
- Portable per-file index: `member-index.jsonl` in that directory, 46,553,908 bytes, SHA256 `d0f30519b5920a3da8f96ea312867fbb2ccbf23c9f4da0ffe25710e7e3af8cd4`. It retains paths, sizes, hashes, modes, modification times and link targets.

## A5 native WCC diagnostic: passed

One snapshot-on, randomized WCC cell ran against the unchanged cit-Patents inputs: 3,774,768 vertices and 16,518,947 edges. Controller and compiled runtime are exact `9f0aa7d2a`; frozen Python runtime/measurement helpers are `6ae2e43a`. Settings: seed 42, canonical labels, 16 partitions, 16 software threads, 30 GiB greedy pool, checkpoint repartitioning enabled, maximum 100 rounds, plan capture disabled. The fresh Python 3.12.6 client has the locked dependency versions, selected imported native ABI/source identities and zero `pysail.extensions` entry points recorded in the [client admission](native-client-admission.json).

The cell converged in 16 rounds. The separate unchanged physical oracle verified all 3,774,768 unique output rows, exact minimum-original-ID component labels, 3,627 components and zero membership mismatches. See [correctness](native-profile-correctness.json) and [independent closure/retention audit](native-profile-independent-audit.json).

All owned parent/child/server processes and groups exited; shared gate and queue locks were released. Complete raw output was copied to `/Volumes/Apo/graph-tests/results/sem-review-20261001/A5-native-profile01/raw-output/` and independently checked: nine files, 14,135,676 bytes. The [raw index](native-profile-raw-index.json) binds every retained file. Source, binary, helper, input and selected client identities agree before/after execution. Failed or uncertain closure would refuse success.

The profiler retained 170 method calls: 51 materializations (`write`), 51 staging touches, 50 removals and 18 counts, with round assignments and edge counts. The [diagnostic receipt](native-profile-receipt.json) retains the raw clocks, phases, arguments and outcomes. Materialization includes touch; nested durations overlap. An extra distinct-component count is a separately named diagnostic phase. The engine includes startup, input snapshots, the public call, that extra count, full raw Parquet export and cleanup; the full oracle and archival copy follow the waited engine exit.

Timed graph input/staging/output use the internal Mac SSD. Binaries, Python client and retained evidence are on Apo. Root corrected the frozen handoff's isolated-Python direct-script recipe by adding the exact frozen helper directory through an explicit `-I -B -c`/`runpy` bootstrap; helper bytes remained unchanged. Exact launch/config and original source-only controls are preserved beside this report.

## Interpretation and remaining work

This is a single instrumented diagnostic on a shared native host. It establishes result correctness and retains the requested method instrumentation. It supplies no paired engine ratio, dedicated-host performance result, Sem-protocol parity or isolated cause for earlier slowdown. The native matched comparisons remain separate work.

The sampled process RSS sum reached approximately 2.53 GiB across 29 samples, including 16 during public-algorithm execution. This is a sampled sum that may include shared pages, rather than a true peak or proof of a 32 GiB OS capacity envelope. macOS provides no Linux cgroup, PSS or guest-steal observation here; those fields are absent/null. Configured software pools are distinct from OS limits and measured extension prepayment.

Independent inspection of the exact historical runtime 561 ELF confirms no static `.symtab` and no `.debug`/`.zdebug` sections: [ELF evidence](runtime-elf-inspection.json), [closed inspection receipt](runtime-elf-host-receipt.json). Its earlier retained build command/profile is optimized release. The reported extra slowdown remains unexplained pending a controlled comparison.

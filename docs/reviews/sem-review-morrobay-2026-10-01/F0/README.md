# F0: native CSR construction diagnostic

All four native cells passed the frozen program's counts and target-sum checksum guards, with no errors or forced cleanup. The [original run receipt](evidence/F0-native-run01/receipt.json) and [independent root audit](evidence/F0-native-supervisor01/root-closure-audit01.json) record unchanged source/input/binary pins, absence of the parent and four child PID/groups, and released locks. This is a checksum-guarded diagnostic; there is no full topology oracle or reusable CSR output.

## Four retained outcomes

Each cell used one fresh native process, four Rayon threads, direct-table ID mapping, and 32-bit dense targets; vertex IDs remain i64 and offsets u64. Directed cells store each input arc once; undirected cells add the reverse of each stored arc without deduplication.

| Cell | Vertices | Input edges | Stored arcs | Declared CSR layout bytes | Child maximum RSS bytes | Guard |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| cit-directed | 3,774,768 | 16,518,947 | 16,518,947 | 126,472,084 | 731,836,416 | passed |
| cit-undirected | 3,774,768 | 16,518,947 | 33,037,894 | 192,547,872 | 667,406,336 | passed |
| graph500-directed | 8,870,942 | 260,379,520 | 260,379,520 | 1,183,453,160 | 8,550,641,664 | passed |
| graph500-undirected | 8,870,942 | 260,379,520 | 520,759,040 | 2,224,971,240 | 8,532,865,024 | passed |

The layout size is the program's arithmetic footprint for IDs, offsets, and dense targets. It is not an exported artifact or whole-process memory. Maximum RSS is the original macOS `/usr/bin/time -l` child observation and includes ingestion, mapping, and temporary buffers; no PSS, cgroup, or memory-cap qualification is claimed.

## Exact source and build

The unchanged six source/handoff files were borrowed from Grust `796b24be244f068554f885cfa33ff2d745c75682`, under `docs/reviews/sem-review-capitola-2026-10-02/F0/`. [Their manifest](evidence/F0-native-supervisor01/source-manifest.json) includes Git blob and SHA identities. The [build receipt](evidence/F0-native-build01/receipt.json) records native x86_64 macOS, Rust/Cargo 1.98.1, `cargo build --locked --release --manifest-path ...`, opt-level 3, thin LTO, one codegen unit, debug 0, stripping enabled, and no incremental build. Original source pins agree before and after.

The binary is 5,206,176 bytes, SHA `86c40b04ade06a1477f3ef4b824a0dee66915e905850a2272ff381d6281f120a`. This report preserves that observed build pin without rereading the binary. The borrowed Capitola records used Rust 1.97.1; the actual compiler differs. No cross-host or Capitola ratio is reported. The unchanged original handoff and historical raw records are retained as provenance, not as new measurements on this host.

## Inputs and boundaries

Cit-Patents and graph500-24 were read from the internal SSD. The original receipts retain the exact Parquet hashes and sizes, checked unchanged before and after the run. Copies of the small input provenance receipts are included; this report did not read or rehash the input payloads. [report.json](report.json) records the retained vertex/edge pins and all four outcomes.

The internal read/map/build clocks belong to the unchanged source. Mapping includes original endpoint-buffer teardown; build includes target-buffer teardown, and the overall internal clock also includes the final checksum assertion. The outer launch-to-exit boundary includes remaining process buffer teardown and excludes input hashing. These clocks measure the diagnostic program, not construction of a retained reusable graph. No additive phase equivalence to Sem or Banda is asserted.

The shared host's page cache was not flushed; one fresh process does not establish cold-cache conditions. Raw clocks remain in the unchanged JSON/stdout/time logs. Absolute timing prose and performance comparisons are withheld.

## Portable evidence

[evidence.tar.gz](evidence.tar.gz) contains the small original sources, metadata, receipts, and logs, including the unchanged supervisor source archive. [archive-members.json](archive-members.json) gives every relative member's bytes and SHA; [artifact-manifest.json](artifact-manifest.json) indexes this report and its expanded evidence. The 13 verified run artifacts total 28,481 bytes. No binary, Parquet payload, Cargo target cache, or retirement archive is packaged.

Prepared at 2026-10-02T11:56:42.645596+00:00.

# Graph500-24 admission and archive proposal

Preparation only: no Graph500 payload was downloaded, no engine was launched,
and no guest/output cleanup was executed here.

The [official catalog](https://ldbcouncil.org/benchmarks/graphalytics/datasets/)
links the [vertex Parquet](https://datasets.ldbcouncil.org/graphalytics-parquet/graph500-24-v.parquet)
and [edge Parquet](https://datasets.ldbcouncil.org/graphalytics-parquet/graph500-24-e.parquet).
HEAD responses were HTTP200: 9,119,859 and 837,233,354 bytes, totaling
846,353,213 bytes (0.788 GiB). [Recorded headers](graph500-24-head.json) retain
ETags and dates; ETags do not substitute for content SHA256. Actual row counts,
schemas, duplicate/loop/isolate properties and SHA256 remain unadmitted.

The following is an illustration using the historical cited counts
`E=260,379,520`, `V=8,870,942`, not a claim about downloaded files. Admission
must substitute actual Parquet footer counts and largest row-group size.

| Item | Formula | Illustrative size |
|---|---|---|
| Original edge logical INT64 payload | `16E` | 3.880 GiB |
| Maximum symmetrized adjacency / sorted pair reference | `32E` | 7.760 GiB |
| Two full vertex-map references | `32V` | 0.264 GiB |
| Scratch plus sealed adjacency, two maps, disk reserve | `64E + 32V + 2GiB` | 17.784 GiB |
| Oracle adjacency seen bitmap | at most `2E` bytes | 0.485 GiB |
| Ten adjacency result logical payloads | `10 × 32E` | 77.599 GiB |

The reference implementation streams edges, fills one owned memmap, applies
in-place quicksort, and deduplicates into the sealed file in 262,144-row
chunks. The structured sort axis is contiguous; NumPy documents zero
additional quicksort workspace and warns that noncontiguous axes can trigger
a copy. [NumPy sort documentation](https://numpy.org/doc/stable/reference/generated/numpy.sort.html).
No full pairset copy or whole-edge Arrow table is used. Quicksort and output
deduplication costs are separately recorded outside the engine timer.

Preparation admits `64E + 32R + 128V + 128B + original_file_bytes + 3GiB`,
where `R` is the actual largest edge row group and `B=262144`. Even substituting
`R=E` in the illustration gives about 28.16 GiB. This is a conservative model
for mapped caches, Arrow decoding, vertex maps and batch headroom; the actual
phase must record process/cgroup memory under its 32 GiB cap. The oracle admits
reference mapped bytes + observed output file bytes + `32R` reader allowance
+ exact seen-bitmap bytes + `128 × 65536` batch work + 2 GiB. It verifies all
rows, retaining the pairset itself; it does not replace comparison with hashes.

For the first Graph500 engine cell, propose **64 GiB free in the guest after
immutable inputs/references are staged**, rechecked before every launch:
about 16 GiB for one large checkpoint plus full export, a provisional 32 GiB
sort/spill allowance, and remaining headroom. Spill is unmeasured; this reserve
does not establish a hard spill bound. Existing reports of roughly 85 GiB free
must be refreshed at admission. Keep the engine envelope at 16 CPU/32 GiB;
failure/refusal/timeout remains a retained outcome.

Propose at least **120 GiB free on Apo for this dataset's run archive**, plus
the existing archives. Eight compared adjacency cells and two warmups alone
can retain roughly 78 GiB of raw logical rows, before maps, references, source
inputs, failed attempts and metadata. Parquet and zstd sizes are unmeasured;
do not budget an assumed compression discount. Increase this reservation or
stop at the next admission failure if observed artifacts require it.

## Proposed archive/cleanup sequence

1. Fetch into a fresh dataset namespace, record URL/time/length/SHA256, inspect
   actual footers/schema, and admit disk/memory before reference construction.
   Keep original input files immutable and separately archived once.
2. Run one owned cell at a time. Retain all failures and exact helper/config,
   raw plans, logs, reference receipt and resource/closure observations.
3. After engine exit, run the full physical oracle. Copy the entire closed
   cell to Apo and verify every copied file against the collected inventory,
   including plans and physical output. Archive failures as well as passes.
4. Write a per-cell tar.zst plus an external archive SHA256 and manifest of
   every member's relative name/length/SHA256. Stream-decompress/read the archive
   to verify all member hashes, reject omitted/extra/duplicate members, and
   confirm the sealed reference and output inventories remain available.
5. Only after owned processes/container are closed and archive verification
   passes, the operator may reclaim that cell's private guest output. Leave
   immutable inputs, references, helpers, source checkouts, unrelated runs and
   uncertain writes intact. Record reclaimed paths/bytes and retain the
   archive/verification receipt. Never remove an unproven stale lock.
6. Recheck guest and Apo capacity before the next fresh ID. Retaining every
   large adjacency result in both guest and host would exhaust an 85 GiB guest
   across the proposed repetitions; verified per-cell reclamation is required.

This proposal concerns the named B8 scratch/results only. It does not authorize
deleting borrowed inputs, old benchmark evidence or photo archives.

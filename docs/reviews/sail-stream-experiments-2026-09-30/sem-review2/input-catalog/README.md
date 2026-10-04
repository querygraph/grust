# Graphalytics Parquet input pointer

The [official Graphalytics catalog](https://ldbcouncil.org/benchmarks/graphalytics/datasets/)
provides the missing public input pointer. It announces Parquet availability in
February 2026 and lists **51 vertex/edge pairs** at
`https://datasets.ldbcouncil.org/graphalytics-parquet/<name>-{v,e}.parquet`.
[Sem's primary article](https://semyonsinchenko.github.io/ssinchenko/post/datafusion-graphs-cc-2/)
links this same catalog and names `twitter_mpi-v.parquet` and
`twitter_mpi-e.parquet`; it does not pin their bytes.

The official linked [statistics sheet](https://docs.google.com/spreadsheets/d/e/2PACX-1vQmFsORNp8OhemIpbAXODkhly2XRkhUuIUTvUv9oHJSgCKQaNNiPFGmHfWPswG3NTUbitAc9nJ3ztRx/pubhtml?gid=1975005458&single=true)
reports these counts and flags. They are source metadata, not measurements of
large Parquet files made by this review:

| Dataset | Vertices | Edges | Directed | Weighted |
|---|---:|---:|---|---|
| graph500-24 | 8,870,942 | 260,379,520 | no | no |
| graph500-26 | 32,804,978 | 1,051,922,853 | no | no |
| twitter_mpi | 52,579,678 | 1,963,263,508 | yes | no |

Only four tiny example objects were downloaded, **1,776 bytes total**: directed
10V/17E and undirected 9V/12E. Their schemas are `id: int64` and
`source: int64, target: int64, weight: double`. Their footers identify
`DuckDB version v1.4.4 (build 6ddac802ff)`. This identifies writer metadata,
not DuckLab authorship, and does not establish every large file's schema.
The complete example bytes, hashes, rows and schema observations are retained
in [tiny-sample-inspection.json](tiny-sample-inspection.json).

The [published website revision](https://github.com/ldbc/ldbc.github.io/blob/123e6d06d12afb40f43f556a156f4117becdb75c/benchmarks/graphalytics/datasets/index.html)
is a documentation pin, not a data release or conversion-code version. Its
Parquet URL inventory exactly matches the fetched live catalog; the two HTML
bodies differ. The linked download script fetches/extracts text archives; it
does not supply Parquet checksums. No immutable checksummed Parquet manifest
or explicit DuckLab conversion attribution was established in this bounded search.

Replace “location and inventory have not been verified” with “the official
catalog and its 102 listed URLs are identified; selection and file identity
remain unverified.” Before Stage A, pin the selected file bytes, schemas,
expected outputs and direction/duplicate/isolate/source contract for both
implementations. A catalog Graph500 name does not establish parity with our
separately generated s24 input. B7 still requires validated immutable borrowed
inputs, ownership/lifetime handling and separate checkpoint-layout guarantees.

[finding.json](finding.json) records the generated UTC timestamp, observations
and unresolved scope. [source-metadata.json](source-metadata.json) retains source
URLs, fetch metadata and original body hashes;
[parquet-url-inventory.json](parquet-url-inventory.json) records links only.
Full article/website/API bodies and original receipts are excluded from
publication and retained byte-for-byte outside the repository;
[publication-exclusions.json](publication-exclusions.json) identifies their
private locations and hashes. No Sem article prose is reproduced here.

Downloads were capped at 2 MB each. No large Parquet input, reference output,
benchmark, remote workload or comparison was run. The main response and
previously frozen prose were not edited. `verify_evidence.py` checks the public
manifest; `--verify-private` additionally verifies all privately retained
original files when that local cache is available.

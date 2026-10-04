# Exact cit-Patents weak-component reference

This preparation uses only the private original files pinned by input receipt
`56bb99e72d5b1c16bebc74e847d77d680131d58f5e03e6f10fb2f85b1123221e`.
It does not download data or execute Sail, GraphFrames, another graph engine,
or a benchmark. Its intended product is an exact membership/count oracle for
a future shared-input pilot, not a Stage A result or historical-byte claim.

The contract is weak connectivity: an edge connects its two declared endpoints
regardless of direction. Every vertex in the official vertex file is retained,
including isolates. Gaps in its positive ID range are not invented vertices.
Inputs are neither mutated nor deduplicated; repeated/reversed edges and
self-loops are processed. No duplicate-edge count is claimed.

The standalone C++ kernel performs union by size with path compression and
tracks each component's minimum supplied ID. It admits only the explicit
positive range within `1..6,009,554`. Its private uint32 indices and sizes are
justified by that checked dataset-specific bound; this is not a generic
signed-ID conversion or a Sail representation change. The canonical output is
private, headerless little-endian signed-i64 `(vertex_id, minimum_component_id)`
pairs, 16 bytes per row, ordered by increasing vertex ID.

`test_reference.py` calls the same production executable and binary parser for
six adversarial valid fixtures, 200 deterministic random cases and six expected
rejections. An independent Python BFS using adjacency sets/queues checks every
membership and component count. Fixtures include isolates, noncontiguous IDs,
duplicate and reversed edges, self-loops, a union root different from the
minimum member, and invalid/truncated input. There are no timing assertions.

`run_reference.py` streams Parquet batches into private binary files, runs the
qualified single-thread kernel, then reads back the full result and checks its
vertex domain, ordering, canonical representatives, counts, isolates and
all-edge label consistency. The full readback is not a second independent WCC
computation: the no-false-merge property comes from the union-find construction
and its tested implementation. It is not an edge-equality-only certificate.

Stages run sequentially; Python waits while the C++ kernel computes. PyArrow
CPU/I/O settings and numerical-library thread limits are one, and Parquet
batch decoding uses `use_threads=False`. The kernel's fixed state is bounded
by 13 bytes times `(maximum_id + 1)`, with no per-edge allocation. Python and
C++ each check observed peak RSS against 512 MiB, and their process-peak sum is
checked below 1 GiB. These are checked observed peaks and bounded allocations,
not an operating-system hard RSS cap. Compiler peak memory is also recorded.

To reproduce in a detached source snapshot with the existing local toolchain:

```sh
/Users/alexy/src/sail-extensions-poc/.venvs/extensions-datafusion/bin/python -I -B \
  build_reference.py /path/to/new-public-build-receipts
/Users/alexy/src/sail-extensions-poc/.venvs/extensions-datafusion/bin/python -I -B \
  run_reference.py /path/to/pinned/input/receipt.json \
  /path/to/new-public-build-receipts/build-receipt.json \
  /path/to/new-public-run-receipts
```

The build receipt pins the compiler executable/version, command, source,
qualified binary and control results. Fresh private directories hold the
executable, fixtures, staged data and membership output. Public receipts hold
hashes, counts, bounds, commands and preparation runtimes only. Original
Parquet files are rehashed before and after; no generated binary/Parquet files
belong in Git. The compiler path is intentionally explicit for this local
preparation, not a portability assertion.

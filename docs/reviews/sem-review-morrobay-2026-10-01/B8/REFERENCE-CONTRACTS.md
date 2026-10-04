# B8 reference and output contract

Preparation and validation run after/before the timed engine process, never
inside it. No engine or Spark module is imported by these utilities.

`prepare_shapes.py --config <JSON>` accepts absolute `vertices`, `edges`,
`output`, and exact `vertices_sha256`/`edges_sha256` pins. It refuses an existing
output namespace. It writes `receipt.json` and these portable artifacts:

| Shape | Raw output schema | Reference semantics |
|---|---|---|
| adjacency | `src INT64, dst INT64` | Exact distinct original and reverse pairset; self-loops retained |
| representatives | `id INT64, representative INT64` | First contraction-round active endpoints, after excluding self-loops; isolates and self-loop-only vertices omitted |
| min-label-initial-round | `id INT64, component INT64` | Every original vertex, including isolates, takes the minimum of itself and undirected neighbors |

The union and array/explode variants use the same reference for their shape.
Min-label's array form is a separately named whole-update rewrite. These are
not complete WCC runs or membership certificates.

The reference recipe follows the pinned [adjacency/update source](https://github.com/querygraph/sail/blob/f3b3ef8fc054ce7788ec2b46ec8b034ccec1f98a/examples/extensions/graph-algorithms/src/pyspark_pecan/algorithms.py#L318)
and [first representative map](https://github.com/querygraph/sail/blob/f3b3ef8fc054ce7788ec2b46ec8b034ccec1f98a/examples/extensions/graph-algorithms/src/pyspark_pecan/wcc_randomized.py#L105).
Independent NumPy carryless arithmetic uses GF(2^64), reduction `0x1b`, seed42
coefficients `a=-4767286540954276203`, `b=2949826092126892291`, and signed INT64
minimum order. Tests use a different polynomial-product/long-division scalar
implementation, including INT64 minimum/maximum, zero and random bit patterns.

Artifacts are `adjacency.i64le`, `representatives.i64le`, and
`min-label-initial-round.i64le`: headerless row-major pairs of little-endian
signed INT64, exactly 16 bytes/row. All are sorted by signed lexicographic
order; maps have unique first-column IDs. Filenames are relative to the
receipt, so the sealed directory can move between hosts. Original absolute
input/output paths remain provenance. Each artifact has row count, column
names, length and SHA256; the caller pins `receipt.json` separately.

`ReferenceReceipt.config`, `inputs_before/after`, actual footer admission,
raw original schemas, isolate count, coefficients, helper hashes, packages
and construction phases are retained. Preparation streams edge batches into
an owned file-backed pairset, sorts its contiguous structured view in place,
and deduplicates/writes bounded chunks. It never holds full source/target
Arrow arrays beside the pairset. Sorting, deduplication, hashing and input
audits are outside the engine timer. Successful scratch is removed only after
the sealed output is flushed and hashed; interrupted scratch is retained.

Supervisor API:

```python
reference = shape_oracle.load_shape_reference(references, shape, receipt_sha256)
correctness = shape_oracle.verify_shape_output(result_directory, reference, shape)
```

`verify_shape_output` accepts the result directory independently of the
parent/child nesting. It checks every physical row, exact names/order/INT64
types, nulls, full row count, all reference values and uniqueness, with no
casts or normalization. Raw nullability/schema and before/after file
inventories are retained. Output order/partitioning is unrestricted.
Adjacency duplicates fail even when the distinct pairset would be right.
Map duplicates fail even when values agree.

The checker streams 65,536-row Arrow batches and uses a one-byte-per-reference
row seen bitmap plus a read-only reference memmap. `Correctness` contains
`outcome='passed'`, `rows`, `unique`, `expected_rows`, `mismatches=0`,
`duplicate_rows=0`, `full_oracle=True`, reference identities,
`result_files/result_files_after`, raw `physical_schemas`, and actual-footer
`memory_admission`. Physical violations raise `Mismatch`; changed or invalid
references raise `ValueError`. An optional `progress` callback retains schemas
and rows examined when verification fails. The standalone checker writes
durable checking/passed/mismatch/error receipts and refuses a reused receipt.

Both preparation and the oracle reject their disclosed memory model above
32 GiB. Estimates include file-backed cache and temporary/batch headroom;
actual process/cgroup peaks still belong in execution receipts. The model is
not a performance measurement or a claim that an untested graph has passed.

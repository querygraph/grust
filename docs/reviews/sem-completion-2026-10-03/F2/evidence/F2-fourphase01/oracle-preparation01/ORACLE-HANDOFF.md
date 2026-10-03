# F2a full physical WCC oracle — source-only freeze

Helper: `f2a_oracle.py`, SHA256 `6514d12838a558336bfbeee0340682f500938e750ccf39698fdf8fb621b2bbc3`. Root owns all actual data scans,
reference provenance, series closure and publication. No engine or original
Parquet payload was opened to author or qualify this source.

CLI: a Python 3.12 environment with NumPy, PyArrow and Pydantic 2:

```sh
python -I -B /Volumes/Apo/graph-tests/results/sem-review-20261001/F2a-native-024-run01/f2a_oracle.py --config /absolute/oracle-config.json
```

The single source imports only dependencies/stdlib, so no sibling import bootstrap
is needed. The caller supplies a unique absent receipt `output` directory. There
is no retry, output overwrite or cleanup of engine artifacts. A failed checker
keeps `receipt.json`; an existing output directory is refused.

## Flat configuration

- `vertices`: FilePin `{path,bytes,sha256}` of original Int64 vertex Parquet.
- `expected_rows`: exact original full vertex count.
- `reference`: `{directory,files:{relative_name:{bytes,sha256}}}`, all physical
  files from the separately closed GF WCC reference. Root binds the prior passed
  A5 post receipt; its complete GF raw inventories are authoritative.
- `outputs`: one or three ordered `{number,directory,files}` objects. Numbers must
  be 1..N; root binds directory N to worker `result-callN` and its sealed record.
- `output`: fresh absolute oracle receipt directory, disjoint from all protected
  paths. Reference/candidate directory aliases are rejected.
- `metadata_pins`: optional extra FilePins hashed before/after. For actual series,
  include this frozen helper, series/config/proof and the prior passed GF producer
  receipt as applicable. The oracle verifies their bytes, while root checks their
  producer/series semantics independently.
- `batch_rows` default 262144; `work_seconds` and `closure_seconds` each default
  3600; `memory_bytes` default 24 GiB. Record actual choices. Deadlines are
  cooperative between IO and vector operations; root owns any outer process wait.

Each raw Parquet file requires exactly two unique names `id` and `component`,
physical Arrow Int64, in either order, with every value non-null. The worker's
explicit timed decimal UTF8-to-long selection is recorded separately. This
checker performs no cast or raw output rewrite. Full schemas/footer+scan counts
are retained. Original vertex Parquet requires exactly `id`:Int64.

All original IDs, raw outputs and the reference are checked in bounded batches.
Ordinal O(V) arrays support the entire signed Int64 range; no maximum-ID array or
E-sized/Python per-vertex dictionary is used. Full unique original coverage and
labels in that domain are mandatory. Every partition is normalized to its
numeric minimum original member with repeated-index `np.minimum.at`; equality
of every canonical row establishes both partition directions. No identical raw
label choice, sampling or hash-only correctness comparison is required.

The memory receipt is a conservative managed-array/row-group admission model;
it is not observed RSS, an OS cap or proof of operation within 32 GiB.

## Positive predicate and scope

`Receipt.outcome == "passed_full_physical_wcc"`, `errors == []`,
`own_identity_closure_passed == full_output_oracle_passed == True`, and identical
`identities_before`/`identities_after`. Both snapshots bind every original,
reference, candidate, configuration, helper and extra metadata file.

`Receipt.config` is the effective typed configuration and `Receipt.configuration`
is the exact config FilePin. Reference `rows == unique_rows == expected_rows`
and its domain/label flags are true. Each checked output binds by `number` to
`Receipt.config.outputs[number-1]`: rows and unique_rows equal expected_rows,
full_original_domain_passed/labels_in_original_domain/
full_partition_equivalence_passed all true, canonical_member_mismatches 0.
Reference engine qualification, actual waited producer closure, input/reference
provenance and preservation to Apo remain separate root proofs. No official
Graphalytics topology/ground-truth or performance verdict is emitted.

Nine bounded offline controls pass, including explicit (-8,2,5) / isolate 0
partitions across three outputs, false merge/split, duplicate IDs in and across
files/batches, omission/unknown/null/label errors, exact schema failures with
schema retention, signed extrema, late mutation, sealed inventory refusal and
durable timeout/fresh-output refusal. Source-only gate logs are in
`oracle-source-gates02/`; repo-context Ruff, format check and strict mypy pass.
Earlier source lint/type and oracle-source-gates01 refusal are retained as source
preparation history. This is not a native data or engine qualification.

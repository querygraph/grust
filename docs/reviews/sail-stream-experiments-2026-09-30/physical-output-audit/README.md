# Physical SSSP output check, prepared only

This helper reads retained Parquet payloads with PyArrow after the producer has
closed. It addresses the specific risk that an older Sail reader can hide a
mixed NaN/finite column using file statistics. It is supplemental to the original
certificate. It does not rerun an algorithm, recompute Dijkstra, inspect graph
edges, prove parent chains or replace the benchmark outcome.

No campaign result Parquet was read during preparation, and no Morrobay command
or workload was launched. The tests use tiny private fixtures only.

## Exact producer and collection boundary

[The contract receipt](producer-contract.json) pins source blobs from controller
`3a9028057c6c6c5034492845926fc4bc18f9626f` and the inspected local evidence.

- `runtime.py:71–74` records each completed result Parquet **basename**, byte
  length and SHA-256. It records neither relative paths nor per-file row counts.
- `traversal_cell.py:24,96` writes the exported result to
  `<arguments.output>/result`. Pecan uses INT64 id/parent/hops and FLOAT64 distance;
  unreachable rows have null distance, parent and hops.
- `run_focused_safe.py:99–110` archives only the cell root's regular files.
  `diagnostics.tar` contains no result Parquet. The result directory remains in
  `sail-extension-targets`; the helper must read that retained directory through
  a read-only mount or a separately collected exact copy.
- The closed compact smoke records two result files totaling 135,918 bytes.
  Logging02 OOM records **no result inventory**. That case is inconclusive for
  this check, regardless of any partial staging files that might remain.

The dense domain is explicit and narrow: `0..N-1`, from the pinned Graph500 or
bounded traversal generator contract. The helper accepts only the original
Pecan SSSP `frontier`/`delta_star` producer shape. It does not generalize to sparse
or signed imported IDs, other engines, a different controller, or arbitrary
schemas. No input Parquet domain is independently re-read here.

## Required evidence and checks

Supply the exact producer receipt and its separately pinned SHA-256, the verified
closed-cell audit and its SHA-256, the expected original cell output namespace,
vertex count and selected source. The helper requires the frozen closed-cell
auditor's successful identity/closure verdict to pin the same receipt and an
exited container. The closure auditor remains responsible for archive, runtime,
source, data-manifest and resource evidence; this helper does not redo it.

The result directory must contain exactly the recorded Parquet inventory.
Missing receipt, closure or result files are inconclusive. Unexpected files,
ambiguous/duplicate basenames, symlinks, wrong hashes/lengths, changed bytes or
wrong schema are integrity errors. Non-Parquet metadata files are ignored.
Unique nested basenames may be located recursively; paths are recorded, never
inferred when basenames collide. This is a trusted campaign evidence checker,
not an adversarial filesystem-race sandbox.

All result hashes, lengths and footer row counts/schema are checked before and
after streaming. Decoded row counts must equal footer counts. A one-byte-per-ID
array checks the complete dense domain exactly, including duplicate/missing IDs.
PyArrow batches count NaN, positive/negative infinity, finite negative distances,
null IDs, invalid parents/hops, unreachable metadata and the source row. Null
distance is a valid unreachable value; negative zero is accepted as zero. Finite
nonroot rows require a parent and hop count in the declared domain/range.
Parent-edge validity, actual reachability, shortest distances and hop recurrence
still require the graph certificate or an independent graph oracle.

The four verdicts are `physical_values_pass`, `physical_values_fail`,
`integrity_error` and `inconclusive`. `producer_outcome` is retained separately.
A physical-value pass on a failed producer does not promote that benchmark run.
It closes only this physical-value/domain gap, even when the producer passed.

## Planned invocation after closure

This is a recipe, **not execution authorization**. Pin the fresh closure-audit
and producer receipt hashes from the independently collected evidence first.
Do not substitute a smoke receipt or compute an expected hash from an unreviewed
remote file immediately before calling the helper.

```sh
python -I -B audit_output.py \
  --receipt /evidence/receipt.json --receipt-sha256 "$PINNED_RECEIPT_SHA" \
  --closure-audit /evidence/closed-cell-verification.json \
  --closure-sha256 "$PINNED_CLOSURE_SHA" \
  --expected-cell-output "$EXACT_ORIGINAL_CELL_OUTPUT" \
  --expected-vertices 16777216 --expected-source 13507776 \
  --result-dir "$EXACT_ORIGINAL_CELL_OUTPUT/result" \
  --output /evidence/physical-output-verification.json
```

For logging03 the original cell root must come from the exact configuration and
closed receipt under `/targets/sail-stream-experiments-20260930/logging03-compact`;
the invocation requires the complete cell path, not that common parent alone.
For a copied result directory only `--result-dir` changes. The original namespace
and inventory remain pinned. Use a new output receipt path; existing evidence is
never overwritten. A zero exit code means only `physical_values_pass`.
The helper rejects an audit-output path inside the retained result directory or
equal to either input evidence path before any scan or write.

## Resource and disk admission

Use the existing pinned Python/PyArrow environment; no install is needed. Arrow
CPU/I/O pools and `iter_batches` are single-threaded, with 65,536-row batches.
Admission is at most 33,554,432 dense vertices (32 MiB ID state), 2 GiB recorded
compressed result bytes and 256 MiB reported uncompressed bytes per row group.
These checks bound the prepared workload; they are not a proof of decoder peak
RSS. The receipt records observed process peak RSS and audit-only elapsed time.

After closure and with no graph workload active, a read-only mount avoids copying
the potentially large result. A separately bounded helper container (for example
one CPU and 2 GiB RAM, no swap) provides a hard limit; a kill means inconclusive
and its outer failure receipt must be retained. Capture actual free disk before
admission. The read-only route needs only small receipt/log headroom; copying
requires at least the exact inventory byte sum plus receipt space and the
operator's retained-artifact reserve. Do not delete data or staging to make this
fit. Hashing before/after plus decoding reads the output approximately three
times. No full dataset, checkpoint directory or graph edge scan is necessary.

Keep this audit outside the original timer. It cannot retrospectively qualify
the shared host's load, paging or timing boundaries.

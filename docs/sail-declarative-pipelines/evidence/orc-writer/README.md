# Public ORC writer

Sail `4f37aef98` (parent `2eae921c5`) activates ORC writing. It takes W4, W5 and the primitive part of W6 from the [writer design](../../ORC-WRITER-DESIGN.md).

| Gate | Result |
| --- | --- |
| fmt, strict Clippy, library tests | pass; sail-common-datafusion 140, sail-data-source 252, sail-execution 245, sail-object-store 38 |
| Frozen regression, harness from evidence/query-function-guard | 300 + 67 |
| New `test_orc_write.py` on Spark 4.2.1 | 24 of 24 |
| New test, `test_orc.py` and the pipelines directory on Sail | 609 of 609 |
| New test on the `2eae921c5` binary | 24 of 24 fail |
| `gates/cross.py`, each engine reading the other's files | 5 codecs each way, 5000 rows, 11 columns; an empty file; 4 files of 300000 rows; no differences |

The cross-engine output was read from the terminal and only `cross.py` is retained. Earlier attempts are not retained as receipts; their failures were test or launcher faults and are listed in the session log: a nullability assertion, a TINYINT overflow in the probe, and `is_jvm_spark` being false for a `sc://` remote.

**Contract.** The footer is written only on an explicit finish, and the upload completes only after the demuxer has been seen to succeed, so a lost input cannot publish a well-formed truncated file. Fault tests cover a failed input, a failed part, a failed abort (kept as context, not the cause), memory denial, a part stalled through cancellation, and a dropped sink future.

**Measured against Spark.** An empty unpartitioned write leaves one schema-only file; an empty partitioned write leaves nothing.

**Limits.**
- Timestamps, TIMESTAMP_NTZ, decimals, arrays, maps and structs are refused with `ORC writing does not support type`; Spark writes them. The native writer lacks decimals and nested types. Native timestamp support exists but needs its own paired evidence. No Spark SDP test uses these types.
- The native encoder's buffers are not reserved, and it emits nothing until a stripe fills, so one file can hold about 64 MiB unaccounted. Queued and in-flight upload bytes are reserved. This is not a heap bound (W2d).
- A failed `complete` after another file committed can leave that file. A retried distributed attempt writes new names, so it can duplicate a completed file; this applies to every Sail file format.
- The worker codec is covered by a round trip only. No distributed run was made.
- **Separate Sail gap:** listing infers partition columns as strings for every format, where Spark infers `int` and others.
- The streaming half of the SqlPipelineSuite grid (`b`) stays open; streaming is disabled publicly.

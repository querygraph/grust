# Vortex capability qualification

Prepared sources only. Root admits the environment, launches each fresh control,
waits its driver, and independently confirms driver/server group absence. No
engine, build, installation, VM, SSH or payload action was performed by the author.

## Exact source and current limitations

Governing Grust: `1bfdf7c37e49c3de09113aeacfb89a6d377cca64`.
Existing optimized native Sail runtime: `9f0aa7d2a50f1258544d37c05dd19b3ff3d915b3`.
Selected Python source: `4b88c8fb4504ab1d2a896c9e49e4a09df4905bbb`.
Its `python/pysail/spark/datasource/vortex.py` is byte-identical at both pins:
10,424 B, SHA-256 `c1cd584719ad546d30ad2408688b1b1450103087fc8b0e55edabd1e356a92e39`.

The source implements a manually registered Python reader, one partition per
file, with top-level view-type normalization. It has no writer method and no
Vortex dependency/registration was found in the selected Rust Cargo/crates
sources. This is a Python data source, not a native checkpoint writer. The
adapter requires PySpark's 4.1 filter API; its current test environment pins
`pyspark-client==4.2.0`. Root reports the actual baseline as PySpark 4.0.1 and
Arrow 21. The two client profiles stay separate.

The [Sail changelog](https://docs.lakesail.com/sail/latest/reference/changelog/)
records the Python reader. The [Spark 4.1 release](https://spark.apache.org/releases/spark-release-4.1.0.html)
introduced Python data source filter pushdown; the [4.2 API](https://spark.apache.org/docs/4.2.0/api/python/reference/pyspark.sql/api/pyspark.sql.datasource.DataSourceReader.pushFilters.html)
requires rejected filters to remain for post-scan evaluation. [Vortex's Python
I/O API](https://docs.vortex.dev/api/python/io) separately supports Arrow writes
and file scans. Standalone Vortex writing cannot be reported as a Sail write.

## Runnable controls

`vortex_models.py` exposes `Plan` and `Receipt`; `vortex-plan-schema.json` is the
generated strict schema. Root supplies exact file pins and fresh paths. The
plan pins must include this helper, models, binary, resolved driver interpreter,
and admitted client/module files. Registered mode additionally requires the
actual loaded adapter file pin and `adapter_python_root`.

Launch from the selected dedicated client environment:

```text
<venv>/bin/python -B <this-directory>/vortex_probe.py --plan <approved-plan.json>
```

For `registered_reader`, set the driver's `PYTHONPATH` to the selected Sail
`python/` directory plus the fresh venv's purelib before launch. The server uses
the plan's same source/purelib path. Admit `pyspark-client==4.2.0`, a concrete
`vortex-data>=0.64,<1` version and compatible Arrow in that fresh environment,
with exact package inventory/hash closure. No Nutmeg wheel is needed by these
controls: extensions are explicitly disabled. Root may use its already-built
0.24 wheel for separate graph qualifications.

1. `native_unregistered`: the original native Parquet reader/writer supplies a
   full typed-row control. Retain actual native Vortex reader/writer errors;
   arbitrary errors are not automatically classified unsupported. A valid
   Vortex read fixture is made only if `vortex-data` exists; otherwise that
   read is explicitly `not_admitted`. Never feed Parquet bytes as Vortex.
2. `registered_reader`: write a tiny Vortex fixture with the Python library,
   verify the complete standalone roundtrip, register the exact Sail reader,
   and export six Sail results to Parquet: all rows, equality, signed-ID range,
   null post-filter, string post-filter and column projection. Every physical
   row and raw field name/type is compared with an independently specified
   fixture. Signed extrema, zero, nulls and strings are included. Attempt and
   retain the registered writer error separately. An unexpectedly successful
   writer downgrades the control because no writer oracle is supplied.

Both use two threads and one 512 MiB greedy Sail pool. These are software
settings, not an OS memory/CPU cap. A 180 s execution deadline, 15 s session-stop
deadline and 30+10 s server cleanup are bounded. The child creates one native
server with a fresh process group; it terminates and waits the direct owned PID
before observing group absence. Forced cleanup, query/oracle failures, changed
pins or uncertain closure prevent a positive outcome. Root must preserve any
remaining owned group and retain failed output namespaces; no broad cleanup.

Positive receipts are `passed_native_format_control` or
`passed_registered_reader_control`, with `errors=[]`, equal before/after pins,
all physical checks true, server actual wait and group-absence proof. Capability
errors are observations in `attempts`, not correctness errors. `not_admitted`
means no server was started in registered mode. The root parent still must
provide its actual waited driver return code and independent PID/group closure.
Raw file inventories include fixtures, partial writer outputs and logs; receipts
are intentionally excluded from their own hash inventory.

## Scope

This qualifies small values and the available API. It supplies no sorted-layout,
write/read performance, distributed Vortex, graph-scale or checkpoint parity
claim. D1's Vortex alternative remains unavailable as a Sail writer unless a
writer is implemented and qualified separately. No server-side graph loop or
PR35 implementation is authorized by this control.

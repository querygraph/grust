# Focused pipeline catalog acceptance

Sail's `scripts/spark-pipelines-tests/catalog.py` runs four batch table checks
through the configured catalog using PySpark[connect,pipelines] 4.2.1:

1. Publish a materialized table and verify its rows and schema.
2. Refresh it and verify replacement rows.
3. Publish a declared column comment and verify DataFrame schema metadata.
4. Replace its columns and verify the new schema and rows.

The table location must stay constant. Each attempt registers a fresh graph,
while retaining the same generated table name and storage URI. The runner drops
its uniquely named table after success or failure and verifies cleanup. It
checks client/server compatibility versions and records SQL, rows, schemas,
locations, case failures, setup errors and cleanup in JSON. Optimized Python is
rejected because these acceptance checks use assertions.

## Reproduce with configured Sail servers

The commands assume the server catalogs already exist and their default database
is available. The optional warehouse argument overrides a Sail session's warehouse;
omit it on servers with static warehouse configuration.

```sh
mkdir -p /tmp/sail-sdp-catalog
python scripts/spark-pipelines-tests/catalog.py \
  --remote sc://localhost:50082 --provider parquet \
  --storage file:///tmp/sail-sdp-catalog/memory-state \
  --warehouse file:///tmp/sail-sdp-catalog/warehouse \
  --report /tmp/sail-sdp-catalog/memory.json

python scripts/spark-pipelines-tests/catalog.py \
  --remote sc://localhost:50083 --provider iceberg \
  --storage file:///tmp/sail-sdp-catalog/lakecat-state \
  --warehouse file:///tmp/sail-sdp-catalog/warehouse \
  --report /tmp/sail-sdp-catalog/lakecat.json
```

Use `--catalog` and `--database` when selecting a non-default configured catalog
or namespace. Credentials and catalog endpoints remain in the server's normal
configuration. The runner imports only the Spark client and standard Python
libraries; it does not import Sail test fixtures or LakeCat code.

## Evidence and scope

[Source-bound reports](evidence/7fd30c4187be2e1c735bf84af583b9fff82b540f/gate.json)
show all four cases and cleanup passing on Sail memory/parquet and LakeCat/Iceberg.
Both servers used the verified engine at 24533f1f0; the runner was tested at
7fd30c4187. A deliberate wrong-answer control records a failed case and successful
cleanup. The LakeCat profile uses a memory store, allow-all test governance and
local files, as recorded in its earlier build receipt.

Full SDP acceptance remains in [the crosswalk](CROSSWALK.md). Persisted views,
failure events, streaming, CDC, distributed execution and durability require
their own coverage. The delta provider option has not been executed in this
profile. No passing percentage or original Scala-suite verdict follows from
these four checks.

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

## Six-pair namespace matrix

`scripts/spark-pipelines-tests/namespaces.py` runs SqlPipelineSuite:759's six batch
producer/consumer name combinations: unqualified/unqualified, unqualified/second
database, unqualified/second catalog, second database/unqualified, second catalog/
unqualified and second catalog/second database. Each has a declared BIGINT
producer and an even-ID consumer. The runner checks both data sets, schemas and
provider metadata. It owns unique names, drops each graph and removes/verifies
its table and namespace metadata after success or failure. Optimized Python and
same-catalog/relative-storage invocations are rejected.

Both catalogs must be configured on the server. The recorded isolated profile
uses primary/secondary memory catalogs plus a LakeCat REST catalog. Example
commands against that profile are:

```sh
python scripts/spark-pipelines-tests/namespaces.py \
  --remote sc://localhost:50084 \
  --primary-catalog primary --secondary-catalog secondary \
  --warehouse file:///tmp/sail-sdp-namespace-matrix/warehouse \
  --storage file:///tmp/sail-sdp-namespace-matrix/state \
  --report /tmp/sail-sdp-namespace-memory.json

python scripts/spark-pipelines-tests/namespaces.py \
  --remote sc://localhost:50084 \
  --primary-catalog primary --secondary-catalog lakecat \
  --secondary-provider iceberg \
  --warehouse file:///tmp/sail-sdp-namespace-matrix/warehouse \
  --storage file:///tmp/sail-sdp-namespace-matrix/lakecat-state \
  --report /tmp/sail-sdp-namespace-lakecat.json
```

The warehouse override is optional and intended for Sail. Catalogs, endpoints and
credentials use normal server configuration; the runner imports only PySpark and
standard Python libraries. Metadata cleanup does not assert general storage-file
reclamation. The [receipt](evidence/b2150a27831dbfc7b285d0d3da62305f8e302b97/gate.json)
records six passes on each profile, an injected acceptance failure after table
materialization with successful cleanup, three invalid-invocation controls and
an independent REST check that the temporary LakeCat namespace is absent. Delta
arguments are accepted but unqualified by these receipts. LakeCat durability,
authentication and distributed operation remain outside this isolated profile.

## Combined catalog, CTE and file-scope fixture

`scripts/spark-pipelines-tests/catalog_scope.py` preserves SqlPipelineSuite:634's
two SQL files and all five output assertions. This includes the batch CTE read
through `STREAM(mv2)`, a join, private view resolution after catalog changes,
two-part output reads and namespace reset for the next file. Unique namespaces,
preconfigured catalogs and explicit providers adapt the fixture to the public
Connect API. Seven outputs (five original assertions and two upstream input
checks), provider/schema metadata, private-view isolation and cleanup are checked.

Use the same options as the namespace matrix, replacing `namespaces.py` with
`catalog_scope.py`. Omit `--database` to create an isolated pipeline namespace.
The [receipt](evidence/8d044db3860b4f55e49543c833246af31e986e2e/gate.json) records passing memory/memory and
memory/LakeCat profiles on Sail `8d044db386`. An independent REST check confirms
the generated LakeCat namespace is absent and the default namespace still exists.
The retained parent run fails specifically at `STREAM(batch CTE)`; the fixture
was not weakened to obtain a pass. Four isolated CTE pipeline assertions also
pass unchanged on Spark 4.2.1 and the new Sail CLI. This does not claim execution
of Spark's original Scala suite or its original two-catalog JVM test substrate.

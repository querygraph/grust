# Native ArcadeDB comparison lane

**Status: qualified on ArcadeDB 26.10.2, awaiting independent site admission.**
Counts, sampling, runtime identity, the coordinator deadline and server-side
cancellation all pass on the pinned `arcadedata/arcadedb:26.10.2` image with
the qualified client in `CLIENT_PROFILES`; the three bundles below are frozen.
The release contains the running-statement listing and termination
([ArcadeData/arcadedb#9680](https://github.com/ArcadeData/arcadedb/issues/9680))
and the fix for long HTTP statements
([#9953](https://github.com/ArcadeData/arcadedb/issues/9953)).
These are not LDBC Benchmark Results.

This is a native engine comparator modelled on the [Neo4j lane](NEO4J.md), not
a Grust adapter. The private harness feature is `arcadedb-native`; the binary is
`grust-lsqb-arcadedb`.

## Protocol

- **Server:** the pinned ArcadeDB image (`arcadedata/arcadedb:26.10.2` by
  platform digest, Temurin 25; the runner accepts others only with `--diagnostic-server-image`, and those runs
  are marked unpinned and cannot be bundled). 8 CPU / 6 GiB without swap, no
  host ports, attached only to the internal `grust-lsqb-arcadedb-qualification`
  network. Image defaults otherwise (heap `-XX:MaxRAMPercentage=75`, ZGC), plus
  three required settings the runner checks without exporting the environment:
  `-Darcadedb.command.timeout=60000` (the server bounds its own work by the
  comparison deadline), `-Darcadedb.server.httpBodyContentMaxSize` of at least
  2 GiB (the import is one streamed request), and a disposable root password.
  The password reaches the client as `--env ARCADEDB_PASSWORD` by name, so it is
  never written into `invocation.json`; the audit checks that.
- **Client:** HTTP/1.1 over a persistent connection (a small built-in client, no
  new dependency). The HTTP API is the only protocol used.
- **Import:** a database the run creates (refused if it exists; never cleared),
  schema from the projected file names, Post and Comment as subtypes of Message
  that keep `kind`, so `(:Message)`, `(:Post)` and `{kind: 'Post'}` all match as
  in the reference model. One streamed `/api/v1/batch` request (ArcadeDB's bulk
  loader) with `expectedRecords`, edges with their `id` and multiplicity. The
  server's created counts must equal the records sent, then
  `MATCH (n) RETURN count(n)` and `MATCH ()-[r]->() RETURN count(r)` must equal
  the dataset totals. Finally ArcadeDB's Graph Analytical View (its
  read-optimised adjacency for traversals) is built once. All of this is inside
  the 600-second load budget and reported as `load_ns`, split into `import_ns`
  and `analytical_view_ns`.
- **Observations:** the shared READY/GO isolated-process protocol, rotating
  W2/R10, 60-second coordinator deadline, a fresh worker per sample. The worker
  opens an HTTP transaction session (`/api/v1/begin`) before READY; after GO it
  runs the query in that session, consumes the single scalar and rolls back
  (`/api/v1/rollback`), all inside the measured interval.
- **Recovery:** the worker sends `X-ArcadeDB-Query-Tag: arcadedb-<pid>-<nanos>`
  on `/api/v1/begin` and on its query, so the server lists the sample's session
  and statement under that tag. After every sample, whatever its outcome, a
  separate connection lists them (`list queries tag <tag>`, `list transactions`),
  terminates exactly those (`terminate query <id>`, `terminate transaction <id>`)
  and polls until neither listing holds the tag, within 15 seconds or the run
  stops. A statement leaves ArcadeDB's listing only after its rollback and
  cleanup, so absence means the server no longer works on it. Then `RETURN 42`.
  Each observation records `cancellation_verified: true`, the terminated
  statement and session ids, work that ended before termination, and zero
  owned statements and sessions remaining; the audit requires all of it.

## Running

```bash
docker network create --internal grust-lsqb-arcadedb-qualification
docker run -d --name grust-lsqb-arcadedb-1 --network grust-lsqb-arcadedb-qualification \
  --cpus 8 --memory 6g --memory-swap 6g \
  -e JAVA_OPTS="-Darcadedb.server.rootPassword=<disposable> -Darcadedb.command.timeout=60000 -Darcadedb.server.httpBodyContentMaxSize=4294967296" \
  <pinned ArcadeDB image>
docker build -f benchmarks/lsqb/Dockerfile --build-arg BENCHMARK_FEATURE=arcadedb-native \
  --build-arg GRUST_SOURCE_REVISION=$(git rev-parse HEAD) -t grust-lsqb-arcadedb .
ARCADEDB_PASSWORD=<disposable> python3 benchmarks/lsqb/run-native-arcadedb.py \
  --server grust-lsqb-arcadedb-1 --image grust-lsqb-arcadedb --source-revision $(git rev-parse HEAD) \
  --output benchmarks/lsqb/out/<new> --scale 0.1 --warmups 2 --runs 10
python3 benchmarks/lsqb/validate-arcadedb-diagnostic.py benchmarks/lsqb/out/<new> --runtime --matched-sampling --summaries
```

Each run needs a fresh server (the import refuses an existing database). Let the
server go idle before starting: the host preflight refuses a busy Docker VM.

## Qualified runs (ArcadeDB 26.10.2)

Client source `cf18446882cd9a629e86715c6bb915625f30b708`, client image
`sha256:7c32b62786151c225d93b57438bb70edd0d4fb6bb3f1c8bdb86f73ec3f315a8a`
(built with `benchmarks/lsqb/Cargo.lock` refreshed by cargo: the committed lock
still pins turso 0.7.2 against the workspace's 0.8, so `--locked` refuses it),
server `arcadedata/arcadedb:26.10.2` linux/arm64
(`sha256:a8d755d0ef09efdaf769765833f15e4ecd15f19bae56f5f94d019bb666e9cbc2`,
engine build `e854692736`, Temurin 25.0.4.1), one Apple Silicon laptop on AC
power, each run started only after the host preflight passed. Each passes
`validate-arcadedb-diagnostic.py --runtime --matched-sampling --require-cancellation`
with the pinned identities: 264 of 264 samples (44 warm-ups, 220 measurements),
no mismatch, timeout or error, cancellation verified on every sample with
nothing left running (every sample rolled back on its own: zero targeted
terminations). The recovery check takes a median 0.55-0.67 ms and is outside
the measured interval. These are not LDBC Benchmark Results.

| Scale | Load (import + view) | q1-q9 medians | slowest attack medians | Bundle manifest (`bundle.json`) SHA-256 |
|---|---|---|---|---|
| example | 0.4 s (0.3 + 0.0) | 1.2-1.3 ms | a6 2.5 ms | `9ee419772d4bb86999a10f67b2225f3fd13f08a516771181b05a8b4a1f101c9c` |
| SF0.1 | 9.8 s (8.1 + 1.6) | 6.9-23.3 ms | a2 106 ms, a1 37 ms, a5 33 ms | `628db39582240ddb44e3aed3d5e50e69bffea88fcf62a3437ef3500fc5c45543` |
| SF0.3 | 27.7 s (19.1 + 8.5) | 16.4-76.8 ms | a2 451 ms, a1 132 ms, a5 130 ms | `a69c419f0cffde1dcdae3b227795ebd3c72365e15603709493d9d869f639fe78` |

Bundles: `bundle-native-arcadedb.py` over each run directory
(`publication_qualified: false`; diagnostic, runtime, matched-sampling,
cancellation and, at SF0.3, internal-network checks verified).

Probes on the same server image and client:
- `recovery-probe`: the stress statement was observed running inside its tagged
  session, `terminate query` acknowledged `terminated` after 114 ms, the worker
  request failed with HTTP 409, the per-sample cleanup then terminated the
  session the statement left open; nothing tagged remained after 140 ms, next
  scalar 42.
- `deadline-probe`: the coordinator deadline fired at 2.000 s (SIGTERM). ArcadeDB
  stops a statement whose HTTP client disconnects, so the abandoned statement
  had already ended when the coordinator listed it; the coordinator terminated
  its session in 32 ms and the next isolated scalar returned 42.

ArcadeDB 26.10.2 leaves the HTTP transaction session open when a read statement
in it is terminated (the `terminate query` answer reports `sessionOpen`); the
recovery step terminates that session explicitly, so the lane does not depend on
the server's session expiry.

Earlier development runs (client `1c11257e`, server built from ArcadeDB `main`
at `2384a46e52`, unpinned) gave the same counts and times within noise.

## Before publication

Independent site admission of the bundles and a publication receipt, as for the
[Neo4j lane](NEO4J.md).

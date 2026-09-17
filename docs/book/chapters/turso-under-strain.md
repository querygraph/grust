# Turso under strain

This chapter documents the Turso adapter as it stands on the
`turso-mvcc-concurrency` branch (pull request #6, head `abea518`), which is
the adapter the next release ships. Everything here was measured; where a
number depends on the engine version, the chapter says which version. The
pinned engine is Turso 0.7.2 from crates.io. Upstream `main` (0.8.0-pre.11 at
the time of measurement) is discussed separately, because it changes two of
the conclusions.

## Two journal modes, two contracts

`TursoConfig::journal_mode` selects the concurrency model, and the choice
decides what the store does when several writers touch the same node.

`TursoJournalMode::Wal` is Turso's write-ahead log: one writer at a time. It
is the faster loader by a wide margin, and under contention it does the
honest single-writer thing: it accepts one writer's transaction and refuses
the rest with a typed busy error. A refusal is not a lost write, so a WAL
store passes the harness's hot-node scenario, but it does so by accepting
between 20 and 120 of 3,200 attempted writes.

`TursoJournalMode::Mvcc` enables multi-version concurrency control
(`PRAGMA journal_mode = mvcc`). Writes run inside `BEGIN CONCURRENT`
transactions with bounded conflict retry, so concurrent writers make
progress. On every graph measured, an MVCC store accepted all 3,200 hot-node
writes. It loads more slowly, and it holds more memory while loading, because
every row version of an open transaction stays resident until it commits.

Turso 0.7.2 converts between the modes on a live database. A database loaded
in WAL mode and reopened as MVCC is accepted; a live MVCC store switches to
WAL and back with `PRAGMA journal_mode`. `tests/wal_to_mvcc.rs` and
`tests/wal_bulk_load.rs` pin both directions, and both pass against upstream
`main` as well. The earlier documentation that said an existing WAL database
is not converted was wrong for 0.7.2 and has been removed.

Choose by workload. A store that is loaded once and then read is a WAL store.
A store that takes concurrent writes after loading is an MVCC store, and the
rest of this chapter is about making its load cost bearable.

## Loading an MVCC store

`put_graph` on an MVCC store no longer runs one transaction around the whole
graph. That design kept every row version of the load in memory until the
end and retried all of it on a conflict; the strain harness measured about
1,500 edges per second that way. Loads now commit in groups of
`MVCC_LOAD_COMMIT_STATEMENTS` batches, so a failure leaves the groups
committed before it, and an MVCC `put_graph` is no longer all-or-nothing.
WAL keeps its whole-load transaction.

### Parallel writers

`set_mvcc_load_parallelism(writers)` runs the load over `writers`
connections, each opened through `connect_shared()`, each taking a disjoint
slice of the nodes and then of the edges under its own `BEGIN CONCURRENT`
transactions. Turso executes one connection on one thread, so this is how a
load uses more than one core; it needs a multi-threaded Tokio runtime. The
harness default is four writers.

Free-running writers defeat Turso's automatic checkpoints: a checkpoint needs
the checkpoint lock, every open transaction holds it in read mode, and with
several writers there is always one open, so the checkpoint returns busy and
row versions accumulate. A web-Google load reached 14 to 15 GB that way. The
writers therefore advance in rounds of `MVCC_PARALLEL_ROUND_GROUPS` commit
groups; between rounds, with nothing in flight, one `TRUNCATE` checkpoint
folds the round into the database file. `set_mvcc_load_round_groups` adjusts
the round size; smaller rounds trade time for memory, and the sweep found no
speed to be gained from larger ones.

The effect, on one host with four writers, against the single-writer loader:

| graph | edges | one writer | four writers |
|---|---|---|---|
| web-Google | 5.1 M | 16,013 edges/s | 30,985 |
| cit-Patents | 16.5 M | 5,526 | 26,661 |
| soc-Pokec | 30.6 M | 4,698 | 26,385 |
| GAP-road | 57.7 M | 2,928 | 27,708 |
| sx-stackoverflow | 63.5 M | 2,929 | 13,464 |

Peak memory during a load fell from about 15 GB to 3 to 7 GB at web-Google
scale. Scaling from one to eight writers measured 326, 220, 171 and 142
seconds for web-Google on an 8-vCPU host: about 35% of the load is
serialized, in the engine's commit path.

### The fastest fill: through WAL

`set_bulk_load_via_wal(true)` makes an MVCC store's `put_graph` switch the
database to WAL, load everything in one transaction, checkpoint, and switch
back to MVCC, whether or not the load succeeds. Journal mode is
database-wide, so nothing else may write during the load; a bulk load before
serving is the intended use. Handles opened later with `connect_shared`
inherit the setting.

This is exactly WAL speed, and WAL loads are 1.5 to 1.7 times faster than
four MVCC writers on Turso 0.7.2. On upstream `main` the gap is wider (see
below), and the via-WAL fill is 2.65 to 3.1 times the parallel MVCC load.
The round trip costs nothing measurable over a plain WAL load at five to
seventeen million edges.

### Foreign keys are off during a load

The Turso schema declares edge endpoints as `REFERENCES nodes(id) ON DELETE
CASCADE`, and `bootstrap` turns `PRAGMA foreign_keys` on for the bootstrap
connection. Until commit `3f1ed19`, that made the result of a load depend on
the writer count: WAL and single-writer MVCC loads ran on the bootstrap
connection and rejected an edge whose endpoint node was not stored, while
parallel MVCC writers, which never set the pragma, accepted it.

`put_graph` now turns foreign keys off on the bootstrap connection for the
duration of the load, outside any transaction, and restores the previous
setting afterwards, whether or not the load succeeded. Every path agrees, and
the behavior matches the Memory reference, where a vertex can exist only as
an edge endpoint. `ON DELETE CASCADE` fires on the connection that deletes,
which keeps the pragma on, so serving semantics do not change: a single
`put_edge` to a missing node is still refused. `tests/dangling_edges.rs`
loads a dangling edge through WAL, one MVCC writer and four MVCC writers,
reads it back identically on each, and checks the restored strictness.

The two endpoint probes per edge were costing more than a third of WAL's
load throughput. With foreign keys off, WAL loads of web-Google rose from
42.9 k to 70.3 k edges per second on Turso 0.7.2 (about 60%); the parallel
MVCC path, whose writers were already unchecked, did not move.

## Concurrent writes and group commit

Under the default `synchronous = FULL`, every MVCC commit fsyncs the logical
log while holding Turso's global commit lock. Sixteen writers each attaching
200 edges to one hot node took about 22 seconds on 0.7.2; Neo4j does the same
work in three to four.

`with_group_commit()` batches concurrent single-statement writes into one
transaction: one fsync per batch of up to `GROUP_COMMIT_MAX_STATEMENTS`
statements, and every acknowledged write is durable when it is acknowledged.
It is not a relaxation of `synchronous`. Handles from `connect_shared` share
the store's committer. On 0.7.2 it takes that workload from 21.1 to 3.2
seconds on one host, with all 3,200 writes accepted and no conflicts.

`set_synchronous` exposes the fsync policy per connection. Bulk loads already
run at `NORMAL` internally (they commit rarely and end in a `TRUNCATE`
checkpoint that fsyncs, so the load is durable when `put_graph` returns), so
the setting matters for single-statement writes, where `NORMAL` removes the
per-commit fsync at the cost of durability on power loss.

### Version scoping: this changes on Turso 0.8

Upstream `main` has engine-level group commit, on by default
(`PRAGMA mvcc_group_commit`, store-wide). There, Grust's client-side committer
becomes a second coordination layer and costs about 19%: the same 16-by-200
workload takes 2.62 seconds with the engine's group commit alone and 3.2
seconds with `with_group_commit` on top. The client committer's numbers are
identical on both engine versions, which is the point: it sets the ceiling.

`set_mvcc_group_commit(enabled)` exposes the pragma. It errors on 0.7.2,
which has no such pragma. The intended policy is: on 0.7.2, use
`with_group_commit`; on 0.8, leave the engine's group commit on and do not
wrap. The default of `with_group_commit` should flip when the pinned engine
moves. The pin stays at 0.7.2 until 0.8.0 is a stable release, because the
facade must not force a pre-release on downstream crates.

## Allocator

`grust-turso` exposes `mimalloc = ["turso/mimalloc"]`, and the facade
forwards it as `turso-mimalloc`. It installs Turso's allocator as the global
allocator of the whole process, which is an application decision, so it is
off by default. Measured on four-writer MVCC loads of web-Google, same host,
alternating pairs: +14% on `main` and +16% on 0.7.2; on WAL loads +9% and
+16%. No harness number in this chapter used it; a deployment that owns its
binary should turn it on.

## What was measured

The adversarial-graph strain harness loads real SNAP graphs and runs hot-node
fan-out (A1), deep paths (A2), sixteen concurrent writers against one hub
(A4), guarded-commit replay (A7) and an operability probe (A12), under nine
hard gates. Every cell in this section passed with every gate at zero.

### Turso against Turso, same host

On quegee (a c5n.4xlarge with no burst credits and less than half a second of
CPU steal per run), the three largest graphs, same binary:

| graph | MVCC load | WAL load | MVCC A4 | WAL A4 |
|---|---|---|---|---|
| com-Orkut, 117.2 M edges | 16,046 edges/s | 24,666 | 3,200/3,200 in 1.82 s | 61/3,200 |
| soc-LiveJournal1, 69.0 M | 19,749 | 31,256 | 3,200/3,200 in 4.81 s | 119/3,200 |
| sx-stackoverflow, 63.5 M | 18,504 | 31,243 | 3,200/3,200 in 6.54 s | 50/3,200 |

WAL loads 1.5 to 1.7 times faster and then refuses 96 to 98% of concurrent
hot-node writes. MVCC with group commit accepts every one. These WAL rows
enforced foreign keys and the parallel MVCC rows did not, so the load ratio
understates WAL; with both sides unchecked, WAL's lead is larger. The MVCC
rows in this table and the next ran eight writers at `synchronous = NORMAL`;
their A4 times measure conflict retries rather than the commit path and are
shown for the acceptance count only. The durable four-writer lane did
com-Orkut's A4 in 5.29 s, all 3,200 accepted, on a different host.

The durable seven-graph MVCC ladder on grust (the harness default:
`synchronous = FULL`, group commit, four writers) is clean on all four core
families on every whole graph up to com-Orkut. It was the first MVCC run to
reach com-Orkut at all: the single-writer loader would have taken most of a
day.

### Against Neo4j, same host

Neo4j 5.26 Community over Bolt in a 6 GiB container, quegee, zero steal:

| | Neo4j | Turso MVCC | Turso WAL |
|---|---|---|---|
| com-Orkut load | 16,800 edges/s | 16,046 | 24,666 |
| com-Orkut A1 / A2 | 144.5 s / 4,082 s | 138.1 s / 1,312 s | 96.8 s / 943 s |
| com-Orkut A4 | 2.90 s, 3,200/3,200 | 1.82 s, 3,200/3,200 | 1.05 s, 61/3,200 |
| com-Orkut peak RSS | 4.9 GB | 22.5 GB | 12.4 GB |
| soc-LiveJournal1 load | 28,062 | 19,749 | 31,256 |
| soc-LiveJournal1 A1 / A2 | 41.8 s / 2,501 s | 29.5 s / 1,065 s | 19.5 s / 773 s |
| soc-LiveJournal1 A4 | 2.90 s, 3,200/3,200 | 4.81 s, 3,200/3,200 | 1.29 s, 119/3,200 |

Turso wins traversal on every graph and passes A7, which Neo4j reports as
unsupported. Load splits by graph: on com-Orkut the MVCC store matches
Neo4j's load; on soc-LiveJournal1 Neo4j loads 1.4 times faster. The A4
column is not a durability-matched comparison, because Neo4j commits durably
and these MVCC rows ran at `synchronous = NORMAL`; in the durable same-host
pairs the strain page counts, Neo4j wins every hot-node-write pair against
the MVCC store and loses five of six against WAL, which accepts far fewer
writes. Neo4j is three to five times leaner in memory throughout. Neo4j has no rows for the two smallest graphs, and the
cit-Patents deep-path cell is vacuous on every backend (no path reaches the
depth), so it is never cited.

### Upstream `main`

Grust compiles and passes all 80 `grust-turso` tests unchanged against Turso
`main` at `19710d58d` (0.8.0-pre.11, 1,859 commits past 0.7.2). Measured
against 0.7.2 on the same host with alternating pairs and the engine version
asserted in every probe:

- WAL loads are 22% faster on `main`; the B-tree write path improved.
- Concurrent single-statement writes are better on `main`, as described
  above.
- MVCC bulk loads are slower on `main`, and the gap grows with the graph:
  5% at one writer and 15% at four on web-Google, 26% at four on cit-Patents,
  and 20 to 23% at four writers on sx-stackoverflow, soc-LiveJournal1 and
  com-Orkut on the same host. Reads on those stores are 4 to 24% faster on
  `main`; only the write path regressed.
- The cause is not group commit, not checkpointing and not the allocator;
  each was ruled out by A/B. A profile puts it in the value comparison inside
  the MVCC index-key compare (`types::cmp_in_column` and
  `read_value_serial_type`, about 31% of the load on `main` against 25.5% on
  0.7.2). Upstream pull request #8385 rewrites exactly that path: against its
  own base it is 29 to 30% faster on this load, and under it the index-key
  share collapses to a single 12% symbol.

The recommended configuration on `main`, all of it existing switches: fill
MVCC stores through WAL, serve with the engine's group commit and without
`with_group_commit`, build with `turso-mimalloc`, and load with foreign keys
off, which the branch already does.

## Methodology, because it decided several numbers

Benchmark hosts that are burstable instances (`t2` on AWS) throttle
silently once their CPU credits are spent; the throttling shows up as CPU
steal, not as an error. One seven-graph lane ran a second engine "1.7 times
slower" for that reason alone and was discarded. Every number in this chapter
was taken with steal recorded, and every engine or configuration comparison
on a burstable host was run as alternating pairs within one run so both sides
saw the same throttling. Absolute throughput comes from the non-burstable
host only.

Hot-node write times at `synchronous = NORMAL` vary from 1.4 to 5.2 seconds
on both engines with no consistent direction; they measure conflict-retry
luck, not the commit path, and are not cited. The write-contention
comparison is the `FULL`-sync alternating A/B.

`/tmp` is a RAM filesystem on the benchmark hosts; every load timing here is
on disk. Run-to-run drift on the same host is about 2%, so any effect under
about 4% needs alternating pairs, and several plausible ideas were rejected
on that basis: deferring secondary indexes during a load (slower), a plain
`INSERT` for loads into empty tables (4% slower), a smaller writer page
cache with GC off (flat), larger rounds (memory, not time), and dropping the
edge identity column from the key (a real 2 to 4%, not worth a stateful
dialect).

## Limitations

The MVCC store holds more memory than the graph: 13 to 23 GB at 60 to 120
million edges with four writers, against 5 to 7 GB for Neo4j. The via-WAL
fill needs exclusive use of the database for the duration of the load. A
parallel MVCC load is not all-or-nothing. Foreign keys are not enforced
during loads, by design. `set_mvcc_group_commit` is meaningful only on Turso
0.8. And the engine's global commit lock, not Grust, is what caps parallel
MVCC loads at roughly 80% of WAL speed on 0.7.2.

# Which graph path when: Pecan, Banda, Grenada or Argentea

The question the 2026-09-29/30 capacity campaign was run to answer: given a
graph, an algorithm and the machines at hand, which of the four Graph Nuts
paths should run it. Every number below comes from a recorded cell in
[`reviews/gn-capacity-2026-09-29.md`](reviews/gn-capacity-2026-09-29.md)
(the running campaign record, with receipts on Morrobay); the inputs are
cit-Patents (3.77M vertices, 16.5M directed edges) and Graph500 Kronecker
graphs at scale 24 (16.8M vertices, 268M edges) and scale 25 (33.6M
vertices, 537M edges), traversed from the sampled highest-degree vertex.
The Linux gate is one 32-core, 100 GiB container on a shared host, so the
times are observations with a spread of about 20% between repeats, not
publishable numbers. Last updated 2026-10-02: a caution and a Capitola comparison added at
the top, and the one-host mode section, both from the graphframes-rs
review; the capacity cells are those of 2026-09-30.

## Read this first: a caution on every time in this guide

Two things found on 2026-10-02 lower the confidence in the absolute times
here, in both directions.

- **The gate was a virtual machine, and the VM was the slow part.** Pecan's
  randomized WCC on cit-Patents takes 51.8 s launch to exit in the gate VM,
  8.9 s natively on the same machine, and 5.0 s on Capitola; graphframes-rs
  takes 13.8 s in the VM and 3.7 s on Capitola.
  Item A5 of [`SEM-REVIEW-2.md`](SEM-REVIEW-2.md) has the evidence. Every
  gate time below is a time in that VM, and the relational paths lost most
  in it. The VM is retired; timing is on the raw machine from here.
- **Build profiles were not recorded per cell.** The extension build script
  (`scripts/build.sh`) builds the host and the native wheels with the dev
  profile, which is about 9 times slower for the host on this workload.
  What the records show:
  - Gate cells: release builds. Codex found the receipt for the gate
    runtime: `cargo build --locked --release -p sail-cli`, optimization
    level 3 and LTO. The gate's slowness for Sail is therefore not a build
    profile; its cause is still open.
  - Capitola cells before 2026-10-02 (the scale-22 column, Argentea's
    1179 s, the write times in `GRAPHFRAMES-RS-PARITY.md`): dev-profile
    builds, the x86 ones under Rosetta. The commands are in the session
    records. Those numbers are not performance numbers.
  - A future cell records its cargo profile in the receipt.

The ranking between paths was exposed too, and has now been re-measured on
Capitola with release builds and the LDBC files. One WCC call, launch to
exit:

| Path | cit-Patents | graph500-24 (260M edges) |
|---|---|---|
| Pecan, default (copies the inputs first) | 5.0 s | 30.4 s |
| Pecan, inputs read in place | 4.1 s | 20.3 s |
| Banda on Grust 0.23.0, text ids: first call | 8.4 s | 139 s |
| Banda on Grust 0.24.0, integer ids, 8 build workers: first call | 1.4 s | 7.3 to 8.2 s |
| Banda, each further call | 0.28 s | 1.2 to 2.0 s |

On Grust 0.23.0 the relational path won a single call, because Banda's
projection took 136 s on one thread through a string map. Grust 0.24.0
(released 2026-10-02) takes integer ids as integers and builds in parallel,
and Banda is then first from the first call at both sizes. So the short
answer below stands again for a graph that fits one process, **provided the
ids are staged as integers (`ids` = `int64`), the extension is built on Grust
0.24.0 and `NUTMEG_WORKERS` is set**; the Banda row is three runs on the
released crates (one run on the release candidate gave 6.8 s). With
text ids on 0.23.0, read it as "Banda when the same graph is queried five
times or more". Pecan and Grenada remain the paths for a graph that does not
fit one process, and they are within about 1.2 times graphframes-rs on this
machine.

## The short answer

| Situation | Run | Why |
|---|---|---|
| The projected graph fits one process's memory budget (up to about 270M edges under an 80 GiB quota today) | **Banda** | fastest on every kernel that finished: 4 to 20 times the relational paths on cit-Patents ranking, 10% faster than the best relational variant on scale-24 BFS, the only path with a scale-24 weighted traversal that completed |
| Iterative ranking (PageRank, WCC) on a graph that fits | **Banda** | one staging pays for every sweep: PageRank 32 to 92 s and WCC 30 to 39 s on cit-Patents against 312 to 729 s relational |
| The graph exceeds one process's budget but fits one host's disk and time (scale 25, 537M edges, today) | **Pecan or Grenada, push-pull or frontier BFS** | the only paths that completed scale 25: push-pull BFS in 1516 to 1610 s at 39 GiB, frontier BFS in 2729 to 2764 s at 75 GiB; Banda refuses (projection over the 80 GiB budget) and Argentea runs out of the 100 GiB container |
| The graph should live as Sail tables and be queried alongside them | **Grenada** | Pecan's plan inside DataFusion: within 10% of Pecan on every variant that finished at scales 24 and 25, so the choice is about integration, not speed |
| No native extension can be installed on the Sail cluster | **Pecan** | pure Spark Connect client code; nothing to deploy on the server |
| The graph exceeds one host and several hosts are available | **Argentea, not yet** | the only path that spans hosts, and it works at scale 22 across two hosts (381 s over the LAN, slower than one host at 268 s); at scale 24 across two hosts it does not complete yet, and on one host it is 1.7 to 3 times Banda's time at 1.5 to 2 times the memory |

## What each path is, and what was measured

### Banda: the resident CSR

One process stages the graph once into a compressed adjacency and runs the
kernels in place, under a memory quota (80 GiB in these cells).

- cit-Patents ranking: PageRank power 32 s, PageRank delta 92 s, WCC 30 to
  39 s; the relational paths 312 to 729 s on the same kernels. Peak memory
  under 4 GiB on every path, so this is a time difference, not a memory one.
- cit-Patents traversal: BFS 31 s against 160 to 164 s relational.
- Scale 24 (`asStaged`, the canonical sort skipped): BFS reference 704 s
  at 31 GiB, frontier 742 s, push-pull 1213 s; SSSP delta-star 1615 s at
  46 GiB, certificate validated. The relational push-pull BFS on the same
  input took 775 to 844 s, so at this scale Banda's lead shrinks to 10%: the
  projection from Utf8 ids to a CSR dominates, which the S1 (Int64
  identity) and S3 (dense u32 projection) work items address.
- Scale 25: refused. The direction-switching kernel's projection alone
  exceeds the 80 GiB budget (`procedure memory budget exceeded`), and the
  canonical staging sort's admission bound refuses even earlier. Banda's
  ceiling today is between 268M and 537M edges on a 100 GiB host.

### Pecan: the portable relational path

Spark Connect client code that expresses each iteration as joins over an
adjacency table; runs anywhere Sail runs, with no server-side extension.

- Scales as far as the engine's spilling does: at scale 25 push-pull BFS
  finished in 1610 s at 39 GiB and frontier BFS in 2729 s at 75 GiB.
- Its reference variant, which relaxes every reached vertex each
  iteration, hit the 100 GiB container on the baseline at scale 24
  (iteration 2) and scale 25 (iteration 4). With the frontier-left join
  fix (`work/s5-frontier-build-side`) it instead loses its stream in
  iteration 2 at scale 25 (41 GiB, no memory event), so the fix did not
  carry it further: the stream loss is the first wall.
- Its reference and frontier variants and its weighted traversal at scale
  24, and now the reference variant at scale 25, lose their gRPC stream
  in iteration 2 (`h2 protocol error: error reading a body from
  connection`) in every attempt so far, including the decision cells with
  the join-side fix, a longer keepalive timeout, worker
  idle removal disabled and a longer stream timeout. Until that is located,
  relational users at this scale should run push-pull BFS, which passes.
- Per iteration it is the slowest path: 20 PageRank iterations on
  cit-Patents take 502 to 729 s.

### Grenada: Pecan's plan inside DataFusion

The same relational algorithm, planned natively over Sail's graph tables.

- Within 10% of Pecan on every variant that finished at scales 24 and 25
  (push-pull BFS 775 s against 844 s at scale 24; 1516 s against 1610 s at
  scale 25; frontier 2764 s against 2729 s). Same failures at the same
  points (reference variant at the container limit, stream loss in
  iteration 2).
- Choose it for integration: the graph and the query stay inside Sail's
  tables and plans. It is not a performance tier above Pecan.

### Argentea: partitions on the workers

The graph is partitioned across Sail workers, each holding its partition's
adjacency natively, and one unrolled Spark job runs the whole traversal as
a sequence of native phases with shuffles between them.

- One host, scale 24: BFS reference 1213 s at 65 GiB on the gate (repeat
  1445 s), 1179 s on Capitola's 8 threads under Rosetta, against Banda's
  704 s at 31 GiB; four times the cores bought nothing, so the time is in
  the per-phase shuffle and materialization, not the kernels. SSSP
  delta-star ran its 30-round cap in 4215 s at 68 GiB with 99.9% reached,
  already 2.6 times Banda's complete run.
- One host, scale 25: the two workers together exceed the 100 GiB
  container in the first phase (killed at 2 h 14 min at 99.8 GiB). The
  partitioned path does not lift the single-host ceiling.
- Two hosts, scale 22: works, 381 s over the LAN against 268 s on one
  host and 120 s for Banda; the cost is the shuffle round trips (about 6 s
  per native phase over the LAN, 53 s over a Tailscale relay), so the
  round cap must fit the graph's depth before a distributed number means
  anything.
- Two hosts, scale 24: does not complete. The unrolled job initialized 22
  of 32 partitions in 20 minutes and then every task failed at once;
  Sail logs worker failures only as a status, so the originating error is
  not yet visible. This needs worker-side error logging and a rerun,
  which is engineering, not another benchmark cell.

## One host: local mode, not a local cluster

For the relational paths on one host, run Sail in local mode. Stage A of the
graphframes-rs review ([`SEM-REVIEW-2.md`](SEM-REVIEW-2.md), section 4)
measured the same Pecan cells both ways on cit-Patents in one 16-CPU, 32 GiB
container, with a full output oracle on every cell:

| Pecan method | Local cluster over local mode (launch to exit) |
|---|---|
| Randomized WCC | 1.26 |
| Min-label WCC | 1.27 |
| Frontier BFS | 1.19 |

A driver and two worker processes on one host add 19 to 27% and no capacity:
the workers share the same memory and cores, and the per-process pools can
sum past the container (Argentea's scale-25 cell above ended that way). A local cluster on one host is
for testing the distributed code path, not for speed. The evidence is one
graph of 16.5M edges; nothing here says how local mode behaves at scale 24.
The harness keeps `--mode` explicit on every cell for that reason.

The cit-Patents times for Pecan elsewhere in this guide (160 to 729 s) are
from the September campaign: a local cluster, input validation on, the older
contraction. With typed Pecan, no validation, the paper's contraction and
local mode, the same graph takes about 48 s for randomized WCC and 18 s for
frontier BFS inside the algorithm call (Stage A diagnostics, shared host).
Banda's cit-Patents times have not been re-measured in that container, so
the first two rows of the short answer still rest on the September cells.

## The ceilings, by scale

| Input | Banda | Pecan / Grenada | Argentea (one host) | Argentea (two hosts) |
|---|---|---|---|---|
| cit-Patents, 16.5M edges | 30 to 92 s, under 4 GiB | 160 to 729 s, under 4 GiB | not run | not run |
| Graph500 scale 22, 67.1M edges | 120 s (Capitola) | not run | 268 s | 381 s |
| Graph500 scale 24, 268M edges | BFS 704 s at 31 GiB; SSSP 1615 s at 46 GiB | push-pull BFS 775 to 844 s; other variants lose the stream or the container | BFS 1213 s at 65 GiB; SSSP over 4215 s at 68 GiB | fails in the first phase |
| Graph500 scale 25, 537M edges | refused (80 GiB budget) | push-pull BFS 1516 to 1610 s at 39 GiB; frontier 2729 to 2764 s at 75 GiB; reference at the 100 GiB limit | out of memory in the first phase | not attempted |

## What would change the answer

- **Banda past scale 25** needs the Int64 identity and dense projection
  (S1, S3): the projection, not the kernel, is what exceeds the budget.
- **Relational reference and frontier variants at scale 24** need the
  stream loss located; it survived every knob tried so far.
- **Argentea across hosts** needs worker-side error reporting, then a
  scale-24 rerun; only then is there a distributed number to compare
  with 704 s (Banda) and 1213 s (Argentea on one host).
- **A dedicated host**: every gate number here shares Morrobay with the
  user's nightly VM and a full disk; repeats spread by 20% and two cells
  were lost to host swap or a copy timeout.

## Not run, on purpose

The queued relational rerun (20 cells), the Banda remainder (8), scale 26
(23), the cit-Patents ranking rerun on the new gate (12) and the
baseline's 7 unrun cells were parked on 2026-09-30 because none of them
changes the table above. Three cells would: the scale-24 relational
reference and frontier BFS reruns, if and when the stream loss is fixed.

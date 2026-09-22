# Changelog

All notable Grust changes are recorded here by date and release. This project
started before the changelog existed, so entries before 2026-06-12 were
reconstructed from Git history, release commits, and the shipped docs.

## Unreleased

### Graph algorithms

- **Each work meter's balance is padded to a whole cache line.** The balance a
  `WorkMeter` spends its admitted block from was a bare `Arc<AtomicUsize>`: a
  32-byte heap chunk sharing a 64-byte line with whatever glibc's tcache had
  freed beside it, and since the projection build went parallel (`db00ee7`)
  that neighbour was the pool's own bookkeeping, written by other cores. Every
  such write took the line from the worker, whose next `lock cmpxchg` on the
  balance had to fetch it back: on the attribution host, 56% of PageRank's
  pull-arc loop sat on that exchange, `path-65536` at sixteen workers ran 2.5
  times slower than 0.22.0 (32.7 ms against 13.1, second call) and sequential
  WCC 10–13% slower; running the same code with tcache disabled recovered
  PageRank, which settled that cause. The balance is now the word followed by
  56 bytes of padding, one whole line, so two balances never share one and
  the balance leaves the 32-byte class; it is not over-aligned, because an
  `#[repr(align(64))]` wrapper measured 1.2–1.5 ms slower on triangles
  `hub-65536` at sixteen workers in three runs and the padding did not.
  Re-measured on the same host against 0.22.0 (second call, medians of
  seven): PageRank `path-65536` at sixteen workers 12.2–12.4 ms against
  13.0–13.2 and 29.1–34.2 before; `path-16384` 9.6 against 9.3 and 17.1;
  sequential WCC `uniform-16384` and `uniform-65536` within 1–2% against
  10–11% before; triangles `hub-65536` at sixteen workers +4.3–4.7% against
  +5.5–6.2% before. The one-worker WCC residue is not the balance's line: a
  shape padded on both sides, which keeps the whole line inside the
  allocation, recovered PageRank equally and left WCC at the old +11%, while
  every other chunk size tried recovered it, and disabling tcache never did;
  what that case responds to is the chunk size class, and why is unexplained.
  A layout test pins the size and offset and checks that consecutively
  allocated balances never share a line. What is counted, the unit at which a
  budget refuses, cancellation, deadlines and every accounting mode are
  unchanged, and results and work counts are bit for bit the same.
- **`WorkMeter::charge` is inlined into every kernel again, as in 0.22.0.**
  The accounting opt-outs put the uncounted meter's deadline sample, with its
  clock read, inline in `charge`, and the body outgrew LLVM's inlining
  threshold: in a thin-LTO release build sixteen kernels called it out of
  line, and union-find's path-halving `root`, into which it was still inlined,
  became an out-of-line call on every edge endpoint of sequential WCC, which
  ran 8–14% slower than 0.22.0 in the default counted mode on the dedicated
  benchmark host. The sample is now a cold, never-inlined call, and `charge`
  and `root` are `#[inline(always)]`. Measured there on the four 65,536-node
  fixtures, sequential counted WCC is 0.3–3.2% from 0.22.0 and BFS from −8.5%
  to +2.7% (second call), both at or below the previous commit everywhere;
  WCC is 16–25% faster than before this change with work uncounted and 20–29%
  with nothing checked. Uncounted BFS is not: 5% slower than before on the
  layered graph and 15% on the path, and no slower on the other two. Work
  counts, the unit at which a budget refuses, cancellation and the uncounted
  deadline cadence are unchanged, and results and work counts are bit for bit
  the same.
- **The uncounted cancellation and deadline tests run a kernel that cannot
  finish.** Both ran PageRank at tolerance zero and unbounded iterations, which
  stops when the residual is exactly zero; at sixteen workers it reached that in
  264 iterations and returned `Ok`, failing the cancellation test on a 16-core
  host and, inside the deadline window, the deadline test once. They now run
  exact betweenness on the same 60,000-node fixture: 4.32e10 units of work fixed
  by the graph, about 33 s at sixteen workers on a ten-core laptop and at least
  0.54 s even at one unit per cycle at 5 GHz on every worker. Cancellation is
  sent once the kernel is seen holding memory beyond the projection, so it is
  past its entry checkpoint, and the test fails if the kernel returned before
  that. The deadline window is four throwaway builds plus 250 ms, and both tests
  fail if the kernel finished rather than being stopped.
- **Arrow results carry the registered schema, not one read off the rows.**
  Result batches were built with `RecordBatch::try_from_iter`, which marks a
  column nullable exactly when that batch holds a null, so the schema changed
  with the data and two batches of one result could disagree: `bfs` reported
  `distance` non-nullable on a batch where every node was reachable, and an
  unweighted `degree` reported `strength` nullable where a weighted one did
  not. `run_on_projection` and `run_with_properties` now hand each cursor the
  kernel's registered outputs through the new
  `ArrowResultCursor::with_declared_columns`, and every batch, empty ones
  included, carries that nullability: nullable for the eight declared-nullable
  columns (`distance` of `bfs`, `dijkstra`, `multiSourceBfs`, `bellmanFord`
  and `longestPath`; `coefficient` of `localClusteringCoefficient`;
  `conductance` of `modularity`; `strength` of `degree`) and non-nullable for
  every other. The registration stays the only statement of it. A batch whose
  columns differ from the declaration, or that holds a null in a column
  declared non-nullable, fails the cursor with `OutputContract`. A cursor used
  directly, without a declaration, reports every column nullable, the one
  claim true of any rows.
- **Integer Arrow columns are Int64, as declared.** `degree`'s `degree`,
  `dfs`'s `visitIndex`, `pagerank`'s and `articleRank`'s `iterations`, `yens`'s
  `pathIndex`, and the `edgeOrdinals` list items of `shortestPaths` and `yens`
  were UInt64, although the registry declares them `Integer` (`i64`). Spark
  has no unsigned types, and the Spark Connect Python client refused the
  column, so `pagerank` and `degree` could not be read from PySpark through
  Nutmeg. The values are indexes, counts and ordinals, far below `i64::MAX`;
  one that did not fit would fail the batch with an error naming the column
  and the value, never wrap. The catalog test now checks every column's Arrow
  type against its declared `ValueType`.
- **ArticleRank**: `RankVariant::ArticleRank` on `PageRankOptions`, and
  `grust.algorithms.articleRank` with PageRank's options and result shape. A
  source divides its score by its outgoing weight plus the mean outgoing weight
  over all nodes, so a citation from a node that cites little is worth less than
  PageRank makes it. The inflated divisor means scores do not sum to one, and
  comparing their magnitudes with PageRank's is meaningless; their order is the
  point. Weighted and unweighted, sequential and parallel, and the test checks
  the kernel against the recurrence written out again densely. Unweighted the
  added mean is the mean out-degree, `arcs / nodes`, taken from the offsets as a
  scalar so the parallel path keeps the two arrays it was reduced to in 0.22.0
  and pays one addition per arc: measured 1.2-1.5% over PageRank on roadNet-CA.
  With the unweighted pull hoist below, that addition is paid once per node per
  iteration, where each share is formed, rather than per arc; the 1.2-1.5% was
  measured before the hoist and has not been re-measured.
- Add **link prediction**: `link_prediction` and
  `grust.algorithms.linkPrediction({metric, node1, node2, communityProperty})`,
  one kernel for NetworKit's six predictors, chosen by `metric`:
  `commonNeighbors` `|N(u) ∩ N(v)|`, `adamicAdar` `Σ 1/ln|N(w)|`,
  `resourceAllocation` `Σ 1/|N(w)|` (both over shared neighbours `w`),
  `preferentialAttachment` `|N(u)|·|N(v)|`, `totalNeighbors` `|N(u) ∪ N(v)|`,
  and `sameCommunity`, 1 when the two nodes carry the same community id.
  Output `node1`, `node2`, `score`. **Candidates are never all n² pairs.**
  By default the kernel scores every pair at distance exactly two (not
  adjacent, at least one shared neighbour; NetworKit's
  `MissingLinksFinder::findAtDistance(2)`), once each with `node1 < node2`;
  otherwise the caller supplies the pairs, as `node1`/`node2` string arrays in
  the procedure, or in Rust as `CandidatePairs` from ids, rows or two Utf8
  columns of Arrow record batches, and they are scored as given, in order,
  adjacent pairs and duplicates included. Undirected projections only, as in
  NetworKit; weights are not read. Neighbours are **sets**, as in
  `nodeSimilarity`: parallel edges collapse and self-loops are dropped, so
  every degree is a count of distinct neighbours. A pair `(u, u)` scores 0
  under every metric, as NetworKit's `LinkPredictor::run` returns; for distinct
  nodes a shared neighbour has at least two neighbours, so Adamic–Adar never
  divides by `ln 1`. `sameCommunity` reads the integer property named by
  `communityProperty` (default `community`, as in `modularity`), rejecting a
  node without one, where NetworKit runs its own PLM partition and GDS scores
  0; the property is requested for that metric only, so the other five run on
  graphs without community ids and through `run_on_projection`. Tested bit for
  bit against the definitions recomputed from `BTreeSet` neighbour sets on 400
  random multigraphs with loops and isolates, every ordered pair and every
  distance-two pair, plus hand-computed cases per metric.
- **PageRank's default path is faster, with unchanged results.** An execution
  that sets no concurrency runs the sequential push loop, which charged the
  work budget once per arc, each charge an atomic exchange on the execution's
  shared counter. It now charges a source's arcs together, in chunks of at most
  1,024 arcs, so cancellation is still observed within 1,024 arcs of a
  high-degree source. The same units are charged in the same order, and a
  refused budget stops at the same unit it did before. The deadline, which is
  sampled once per 1,024 charges, is now read about once per 1,024 sources or
  arc chunks rather than once per 1,024 units.
- **The unweighted parallel PageRank reads one array per arc instead of two.**
  Each source's `score / out-degree` is formed once per iteration in the pass
  that already sums the dangling mass, instead of on every arc. It costs one
  more f64 per node (about 15.7 MB on roadNet-CA's 1.97 million nodes),
  admitted like the kernel's other scratch. The weighted pull is unchanged.
- Scores, iteration counts, residuals, the work charged and the unit at which a
  budget refuses are pinned to their previous bits by
  `tests/pagerank_pinned.rs`, on the push loop and on the pull at one, two and
  sixteen workers.
- Add **Yen's k shortest paths**: `yens` and
  `grust.algorithms.yens(source, target, {k})`, the `k` shortest **loopless**
  paths between two nodes, built on Dijkstra as Yen 1971 describes. Output is
  `shortestPaths`' shape — `sourceNodeId`, `targetNodeId`, `totalCost`,
  `nodeIds`, `costs`, `edgeOrdinals` — with a `pathIndex` column carrying the
  path's rank from zero. GDS calls that column `index`, which is a reserved
  word in this dialect and so would have to be yielded as `` `index` ``; the
  column is named `pathIndex` rather than make the spelling every caller
  reaches for first a syntax error.
  **Returning fewer than `k` paths is the correct answer** when fewer exist,
  not an error: the paths are simple, so there are finitely many. `k` must be
  at least 1. **Ties break toward the smaller node sequence**: paths are ranked
  by total cost with `f64::total_cmp`, and equal costs by their node rows read
  from the source, lexicographically. That order is reached rather than
  approximated — each spur search returns the lexicographically smallest of the
  minimum-cost paths available to it, walking only arcs that lie on a shortest
  path and checking, where a zero-weight arc makes it necessary, that the
  target is still reachable before committing to the smaller row. A path is a
  sequence of nodes: parallel edges collapse and each hop reports the cheapest
  edge joining its two nodes, a self-loop can never appear, `source == target`
  is the zero-hop path of zero cost, and an unreachable target is no paths at
  all. Costs are summed along the path from the source, so a reported cost is
  exactly the sum of its hop weights in that order. Weights must be
  nonnegative, as for every Dijkstra-based kernel. Tested against exhaustive
  enumeration of all simple paths on 1,800 small graphs in all three
  orientations — an oracle that shares no code with the kernel — for path
  identity and not merely for cost, with hand-computed cases beside it.
- Add **all-pairs shortest paths**: `all_pairs_shortest_paths` and
  `grust.algorithms.allPairsShortestPaths({sourceNodes})`, the shortest
  distance for every reachable ordered pair, with columns `sourceNodeId`,
  `targetNodeId` and `distance`. **It never forms the n×n matrix**: the result
  is a pull cursor that runs Dijkstra from one source at a time over a single
  reused workspace and hands that source's pairs out before starting the next,
  through both the Arrow cursor and the Cypher row cursor. Admitted memory is
  the projection, four O(n) buffers and the batch being consumed, whatever the
  number of pairs; the test shows the peak does not move after the first pair,
  and that four times the nodes (sixteen times the pairs) costs under twice the
  peak. Work is charged per heap operation and arc as in `dijkstra`, plus one
  unit per pair produced, so a work budget stops a run partway rather than
  after it. **Unreachable pairs are omitted**, not returned as null: the set of
  targets is the projection, so a missing row says the same thing, and nulls
  would make every source cost O(n) whatever it reaches. Each node reaches
  itself at zero, as in `dijkstra`. Sources come in projection row order, and
  targets in row order within a source. `sourceNodes` restricts the sources
  (targets are always every node); the order it names them in does not matter,
  a duplicate or an unselected id is rejected, and an empty list selects
  nothing. Parallel edges count at their cheapest, self-loops change nothing,
  and weights must be nonnegative, as for every Dijkstra-based kernel.
  Sequential. Tested pair by pair against `dijkstra` called independently per
  source on 1,200 small graphs across all three orientations, with
  hand-computed cases beside it.
- Add **k1 colouring**: `k1_coloring` and
  `grust.algorithms.k1Coloring({maxIterations, seed})`, yielding `nodeId`,
  `color`, and the `colorCount`, `iterations` and `converged` scalars. Each pass
  gives every uncoloured or conflicted node the smallest colour none of its
  neighbours holds, reading the colours the previous pass left, and then queues
  the lower-priority endpoint of every edge whose ends now agree. Priority is
  row order, or one seeded shuffle of it from the counter-based generator, never
  thread order; the result is a pure function of the projection and the seed.
  Because the higher-priority endpoint of a conflict keeps its colour, a graph
  of `n` nodes is conflict-free within `n` passes, and `iterations` and
  `converged` report which of that and `maxIterations` ended the run — the
  default of 10 passes can stop a large graph early, and it says so rather than
  presenting a colouring with conflicts as final. A node's colour never exceeds
  its number of distinct neighbours, so at most `Δ + 1` colours are used; the
  chromatic number is not sought and no claim is made about how near it this
  comes. **Undirected projections only** — a directed one is rejected rather
  than silently symmetrized, as `kCore` rejects it. Self-loops are ignored, a
  node not being its own neighbour here, and parallel edges impose the one
  constraint their endpoints already impose. Weights are never read, though a
  signed projection is still refused as every kernel but `bellmanFord` refuses
  one. Sequential. The test checks the two properties — no edge joining equal
  colours, and the `Δ + 1` bound against a maximum degree recomputed from the
  edge list — on 3,000 random multigraphs, alongside a triangle, a path, a star,
  `K4`, isolates, loops and the empty graph, each checkable by inspection.
- Add **longest path in a DAG**: `longest_path` and
  `grust.algorithms.longestPath`, the heaviest directed path ending at each
  node, by dynamic programming over a topological order. The empty path counts,
  so every node scores at least zero and a node no arc enters scores exactly
  zero; weights come from the projection, and without them every arc weighs one,
  which makes the distance the hop count. Parallel arcs compete like any others
  and the heaviest wins. Columns are `nodeId`, `distance`, `hops`, `cycleIndex`
  and the `cyclic` scalar.
  A **cycle is a result, not an error**, as for `topologicalSort` and
  `bellmanFord`: with a cycle no path is longest, so distances and hops are
  withheld as null and the cycle itself is returned as a witness whose arcs a
  caller can check, ordered by `cycleIndex` and repeating no node. An undirected
  projection turns each edge into two arcs, so it is almost always answered with
  a two-arc cycle; a self-loop is a cycle of one. The kernel refuses a signed
  projection like every kernel but `bellmanFord`, although its recurrence would
  survive negative weights — the refusal is the catalog's rule, stated in the
  kernel's documentation rather than implied. Sequential, deterministic,
  `O(n + m)`, every arc scan charged. Tested against exhaustive enumeration of
  every path on 9,000 small graphs, against the same recurrence recomputed over
  an independent Kahn order on larger layered DAGs, and on hand-computed cases
  where a greedy extension of the best node so far gives the wrong answer.

### Node properties

- Add `node_property_options(name)`: the options through which a kernel names
  the node properties it reads, each with its declared kind and missing-value
  policy, readable before any call exists. `PropertyOption` is now public.
  `node_property_requests` already answers for one validated call, but
  validation fills an absent option from its default, so its answer always
  names some column. An embedder that builds its own graph, such as Nutmeg
  probing a kernel's result schema on a three-node graph, needs to know which
  columns to stage and of what kind before it builds that call. Otherwise the
  defaults name columns the graph does not have and a required property
  refuses the call.
- The procedure layer can request a node property for some option values only
  (`linkPrediction` asks for its community under `sameCommunity` alone), and
  `run_on_projection` now runs a property-reading kernel whose call reads no
  property, with `NodeProperties::empty`. `node_property_options` still lists
  such an option for every call; `PropertyOption::needed(args)` says whether a
  call with those validated arguments reads it.

### Execution accounting

- **Child executions: one memory budget, many independently stopped queries.**
  `ExecutionContext::child(ChildLimits)` makes an execution that draws memory
  from its parent's budget and keeps its own work counter, work budget,
  cancellation and deadline, so an embedder serving concurrent queries can
  bound the whole process by one budget without every query sharing one
  cancellation flag and one contended work counter. `ChildLimits` sets an
  optional memory sub-limit (no larger than the parent's limit), a work
  budget, a deadline (clipped to the parent's), an accounting mode, and
  optionally batch rows and concurrency; the rest is inherited.
  `ExecutionContext::parent()` names the parent. Children nest.
- **Memory is admitted at every level in one decision.** A child's charge
  counts against its own sub-limit, if it has one, and against every
  ancestor, and siblings cannot jointly exceed their parent. A child without
  a sub-limit asks its parent first and counts the bytes only once admitted;
  one with a sub-limit claims them against its own limit, asks the parent,
  and withdraws the claim if the parent refuses, so the root is only ever
  changed by admitted bytes. A charge that fails at a sub-limit retries once
  under that child's exclusive admission lock, so a claim the parent was
  about to refuse cannot make a charge that fits fail; a root still admits
  with one compare-exchange and takes no lock. Bytes return to every level
  when a reservation or account drops, and a child's cumulative charges return
  to the parent when the child drops. Each level reports its own live and peak
  bytes, a parent's including its children's.
- **Cancellation reaches down, never up.** Cancelling an execution cancels
  every descendant and wakes their `cancelled()` waiters; a child created after
  its parent was cancelled starts cancelled. Cancelling a child reaches neither
  its parent nor its siblings. A child of an interruptible execution must
  itself be interruptible, and asking otherwise is `InvalidArguments`; under an
  uninterruptible parent a child may be either.
- **Work is not aggregated.** A child's work is counted on its own counter
  against its own budget; the parent's usage and work budget cover only the
  work charged to the parent. Aggregating exactly would put every child back on
  one shared counter.
- **`MemoryReservation::shrink(bytes)`** lowers a reservation's charge and
  returns the excess at once, through every level of a child, for a caller that
  reserved an upper bound and now knows the real size. The peak keeps the
  bound. Clones share the charge, so racing shrinks release each byte once. A
  reservation never grows.
- Tests: siblings racing a parent's budget, and threads racing one child's
  sub-limit, each with a monitor checking every level and holdings kept until
  every thread is done so the pressure does not depend on the scheduler;
  replacing the two-level admission with two separate checks fails both. Exact
  admission across racing children, a claim the parent refuses
  never refusing a charge that fits, cancellation in both directions including
  children created while the parent is cancelled, per-child work budgets
  racing meters, deadlines, modes, and PageRank on racing children
  bit-identical to a root at one and four workers. The test that a refused
  claim never refuses a charge that fits keeps charging until a thousand
  refused claims have run beside it: with every core saturated its charger
  twice in 300 runs finished before any of them started, and the test failed
  as vacuous.
- **A cached projection runs its kernels on a query's own execution.**
  Every kernel takes its execution from `GraphProjection::execution()`, which
  was the execution the projection was built on, so a cached projection ran
  every query's kernel on one shared cancellation flag and one shared work
  counter, and child executions could not help. `GraphProjection::with_execution(
  &context)` returns a view that shares the projection's data — adjacency,
  weights, node and edge tables, and the transpose, built or not — and copies
  none of it; kernels on the view admit their scratch and results against
  `context`, charge their work to its counter and budget, and stop at its
  cancellation and deadline. `GraphProjection::owner()` names the execution
  the projection was built on; `execution()` is the owner unless the handle is
  a view. `context` must be the owner or a descendant of it, and anything else
  is `InvalidArguments`: a descendant admits every byte against the owner's
  budget too, is cancelled when the owner is, and never outlives its deadline,
  so the budget the projection lives in still bounds, and stopping the owner
  still stops, everything done with its data. `ExecutionContext::is_within(
  &ancestor)` answers that question by identity.
- **State a projection keeps is its owner's, whichever view builds it.** The
  transpose that in-arc kernels build on first use is cached in the shared
  data and outlives the query that built it, so every byte of it, and of the
  build's scratch, is admitted by the owner and released only when the
  projection's last handle drops; a query with a one-byte memory sub-limit can
  build it. The build itself is the query's: its work is charged to the view's
  execution, it uses the view's worker count, and cancelling the view, or a
  work budget that runs out, stops it, keeps nothing, and returns every byte
  to the owner, and the next kernel that needs it builds it again. The
  transpose is the only lazily built state a projection holds.
  `prepare_incoming()` on the owner still builds it at staging, charged to the
  owner, where no query pays for it.
- Tests (`tests/projection_views.rs`): which executions may run a view; the
  transpose built through a child's view, by `prepare_incoming` and inside a
  kernel, held by none of the query and all of the owner after the child is
  gone, and released with the projection (charging it to the child instead
  fails both); a build refused by the query's work budget keeping nothing;
  PageRank through a view bit-identical to the owner, with the same work, on
  the push loop and on the pull at one and four workers; two concurrent
  PageRanks on one cached projection through two children, one cancelled while
  both run and the other finishing with the owner's bits and exactly its own
  work, the owner charged nothing; a view's deadline its own, and cancelling
  the owner reaching every view.
- **An execution can run with work accounting turned off, by name.**
  `ExecutionContext::with_accounting(limits, accounting)` takes an `Accounting`
  with two independent switches, `work` (`Counted` or `Disabled`) and
  `interruption` (`Observed` or `Disabled`), and constants for the useful
  combinations: `Accounting::COUNTED`, `Accounting::WORK_UNCOUNTED` and
  `Accounting::UNCHECKED`. `ExecutionContext::new` is unchanged and counts work;
  `work_units: usize::MAX` still means "no budget, still counted" and never
  implies an opt-out. The purpose is a like-for-like row when comparing with a
  library that performs no accounting, reported as an additional row rather than
  in place of the counted one.
- **What is given up.** With work uncounted, there is no work budget and no work
  total: charges skip the shared counter, meters take no block grants and are
  never registered, and nothing enforces how much work a kernel may do.
  Cancellation and the deadline are still observed, at the same cadence as
  before. With interruption disabled as well, **nothing can stop a running
  kernel**: no charge, checkpoint or reservation reads the cancellation flag or
  the clock. Memory admission is never disabled; every mode still reserves
  before allocating and fails at its memory limit.
- **A limit the mode cannot enforce is refused at construction** rather than
  accepted and ignored: a finite `work_units` with uncounted work, or a deadline
  with interruption disabled, is `InvalidArguments`. `cancel()` on an execution
  with interruption disabled returns `Unsupported`, and a `cancelled()` waiter
  completes at once with the same error instead of waiting forever.
- **Breaking:** `ResourceUsage::work_units` is now a `WorkCount`, either
  `Counted(n)` or `NotCounted`, so an uncounted run cannot be read as zero work.
  `ResourceUsage::counted_work()` returns `Option<usize>`, and
  `ResourceUsage::accounting` and `ExecutionContext::accounting()` report the
  mode, which displays as `counted`, `work-uncounted`, `uninterruptible` or
  `unchecked`.
- Kernel results are bit-identical in every mode. The tests compare PageRank
  (weighted and unweighted), degree, BFS, multi-source BFS and weakly connected
  components across all four modes sequentially and at one, two and sixteen
  workers, and check that the fixture reaches the parallel kernels. Timings are
  not part of this change.

### Projections and results

- Add `GraphProjection::prepare_incoming`: build a projection's transpose now,
  rather than inside the first kernel that reads it. Until now the first such
  kernel paid for it — PageRank's pull path among them — so an embedder that
  caches projections, as Nutmeg does, had the build land inside a user's query,
  and a timing of one kernel saw a one-off build folded into it. It is admitted
  and charged exactly as before, just earlier; later kernels share it, a second
  call builds nothing, and results are bit-identical either way. Free on an
  undirected projection, whose rows already mirror.
- **Projections build in parallel** when the execution asks for concurrency
  and the graph clears the parallel floor, with the result byte-identical to
  the sequential build at every width: offsets, targets, weights and edge slots,
  for the projection's own adjacency and for the transpose `prepare_incoming`
  builds. Edge validation proves ordinals distinct with one bit per ordinal
  instead of a hash set (37.7 s of a 63.4 s com-Orkut build went to that set)
  and checks endpoints and weights in parallel. Degrees are counted in chunks
  into per-chunk rows and summed, with no atomics. Arcs are filled by row
  range: each worker owns a contiguous range of rows, and so a contiguous
  slice of every array, and walks the whole input in order placing only its
  own rows' arcs, so every row is written by one worker in the sequential
  order. Peak accounted memory is the sequential build's, unchanged: the
  counting table (at most eight bytes per edge) is released before the arrays
  are allocated. Work totals are unchanged, and a work budget that would run
  out during a parallel pass takes the sequential pass instead, so it is
  refused at the same unit with the same count at every width. Laptop ratios
  (10-core Apple laptop, 1.5M nodes, 30M edges, whole `from_topology`):
  directed 3.2-3.4 s sequential to 0.8-0.9 s at eight workers; undirected and
  weighted 5.0 s to 1.2 s; the transpose, read as PageRank's first call less
  its second, about 0.42 s at one worker to 0.20 s at eight. Not measured on the
  reference server.

## 0.22.0 — Mysid — 2026-09-21

### Graph algorithms

- Add **A\***: `astar`, `astar_haversine` and
  `grust.algorithms.astar(source, target, {latitudeProperty, longitudeProperty})`.
  Shortest path to one destination, guided by an estimate of the cost still to
  come. The estimate must never exceed the true remaining cost and must be in
  the weights' units; given that, the path is the one `dijkstra` returns, which
  is the oracle the kernel is tested against. A node may be settled twice, so an
  admissible but inconsistent estimate still yields a shortest path.
  `AStarPath::settled` reports how many nodes were settled, so the saving is
  measured rather than assumed. The registered procedure's heuristic is
  great-circle distance from two coordinate properties, **admissible only where
  the weights are distances in metres**; a latitude outside ±90° or longitude
  outside ±180° is rejected, though a latitude and longitude swapped within
  range cannot be detected. An overestimating heuristic returns a real path that
  is not the shortest, which the kernel cannot detect and its documentation
  says so. This closes Tier A of `docs/goals/graph-analytics-catalog.md`.
- Add **Bellman-Ford**: `bellman_ford` and `grust.algorithms.bellmanFord(source)`,
  single-source shortest paths when weights may be negative. A negative cycle
  reachable from the source is a **result, not an error**: distances are then
  withheld, because none past the cycle is a minimum, and the cycle is returned
  as a witness a caller can check (`cycleIndex` orders its nodes; the arcs exist
  and sum below zero). An undirected edge of negative weight is a negative cycle
  of two arcs and is reported as one. Queue-based, sequential, deterministic,
  every arc scan charged. Tested on 12,000 small signed graphs against exhaustive
  enumeration of simple paths and cycles, with each reported witness verified
  independently, and against `dijkstra` wherever Dijkstra is allowed.
- Add **FastRP node embeddings**: `fast_rp` and `grust.algorithms.fastRP`, with
  `embeddingDimension`, `iterationWeights`, `nodeSelfInfluence`,
  `normalizationStrength` and `seed`. Each node draws a very sparse random
  vector (`±√3` with probability 1/6 each), every round replaces it with the
  weighted mean of the vectors its arcs reach, and the rounds are summed at unit
  length with their weights. Entry `j` of node `v` is a pure function of
  `(seed, v, j)`, so the embedding is identical at any pool width. It is the
  first vector-valued result: result tables gain a fixed-length `Float32` column,
  emitted as Arrow `FixedSizeList<Float32>` and as a float list to Cypher. The
  test rebuilds the random vectors from a round-zero run and repeats the whole
  computation densely in double precision. No claim is made about embedding
  quality.
- Add **maximum flow and minimum cut**: `max_flow`, and
  `grust.algorithms.maxFlow(source, target)` and `.minCut(source, target)`.
  Capacities are the projection's weights, parallel edges are separate
  capacities, and self-loops and zero capacities carry nothing. `maxFlow`
  returns one row per edge carrying flow, oriented the way the flow runs, so an
  undirected edge reports its net flow; `minCut` returns each node's side, the
  source side being what the source still reaches once the flow is in place.
  Dinic's algorithm, iterative, sequential. With integral capacities every value
  is exact; with fractional ones the flow is feasible and maximal up to
  rounding. The test compares the value with the cheapest of every possible cut
  on 7,500 random networks and checks capacity and conservation on the reported
  rows. Procedures can now declare a second positional node argument, `target`.
- Add **Leiden** community detection: `leiden` and `grust.algorithms.leiden`,
  with Louvain's options and result shape. Between moving and coarsening it
  refines each community from singletons, merging a node only while it is still
  alone, only into a neighbour's group, and only when modularity does not fall,
  so **every community is connected** — weakly, on a directed projection, and
  never through a zero-weight arc. The result is always the refined partition,
  so the guarantee holds however the run ends, `maxLevels` included. Refinement
  is greedy, the zero-temperature limit of the paper's randomised rule: it
  keeps connectivity and reproducibility and gives up the paper's asymptotic
  optimality guarantee; there is no `theta`. Tests assert connectivity and
  honest modularity over 4,500 random runs with zero weights, loops and parallel
  edges, never above the brute-force optimum, and exact recovery of planted
  cliques.
- Add **eigenvector centrality**, **Katz centrality** and **HITS**:
  `eigenvector`, `katz`, `hits` and the procedures of the same names, each
  reporting `iterations`, `converged` and `residual` as `pagerank` does, never
  asserting convergence silently. Influence flows along the projection's arcs.
  Eigenvector iterates `(A + I)x` rather than `Ax`: same eigenvectors, but it
  converges on bipartite graphs where plain power iteration oscillates. Katz
  does not refuse an `alpha` above the cheap `1 / (largest in-strength)` bound,
  which would reject many valid values; a run that does not settle says so, and
  one that overflows fails and names `alpha`. Each node pulls from its
  neighbours over fixed chunks of 4,096 nodes on the caller's rayon pool, so
  scores, residuals and charged work are bit-identical at any width. Tests check
  the defining equations with dense linear algebra: `Ax = λx`, `MMᵀa = λa`,
  and Katz against Gaussian elimination.
- Add **minimum and maximum spanning forests**: `spanning_tree` and
  `grust.algorithms.spanningTree`, with `objective` and `sourceNode`. Kruskal
  with union by size and path halving, on an undirected projection. Ties go to
  the smaller edge ordinal, so edges are in a total order and the forest is the
  greedy one for it: the same projection always gives the same edges, not one
  of several equally light ones. `sourceNode` keeps the tree of that node's
  component, which is what a Prim run from it returns. Only the sort runs on
  the rayon pool, and its order is total, so nothing depends on the pool. The
  test finds the expected forest by exhaustive search over edge subsets, with
  heavy ties, for both objectives.
- Add **bridges**, **articulation points** and **biconnected components**:
  `biconnectivity`, and `grust.algorithms.bridges`, `.articulationPoints` and
  `.biconnectedComponents`, from one iterative low-link pass on an undirected
  projection. The pass tracks the edge it arrived by, not the node, so parallel
  edges are a cycle of two: neither is a bridge and both share a component.
  Self-loops disconnect nothing and lie in no component. Edge rows carry
  `sourceNodeId`, `targetNodeId` and `edgeOrdinal`; a component is named by the
  smallest edge ordinal in it. Each output is checked against its definition —
  remove the edge or node and recount, or enumerate every simple cycle — on
  every simple graph of up to five nodes and 4,000 random multigraphs, and a
  million-node path shows the pass does not recurse.
- Add **node similarity**: `node_similarity` and
  `grust.algorithms.nodeSimilarity`, with `metric` (`jaccard`, `overlap`,
  `cosine`), `topK`, `topN`, `similarityCutoff`, `degreeCutoff` and
  `upperDegreeCutoff`. Nodes are compared by the *distinct* nodes their arcs
  reach: parallel edges collapse into one neighbour, present or not without
  weights and carrying their summed weight with them, which differs from the
  degree-style kernels. A pair sharing nothing is never emitted; a kept pair
  appears from both sides because `topK` is per `node1`. Cost is the number of
  (node, shared neighbour, node) triples, every one charged, so the work budget
  stops the quadratic hub case. Rows and charged work are identical at any pool
  width, and the two directions of a pair carry the same bits. Checked row for
  row, order and bits included, against an O(n²) recomputation over 3,600
  random runs.
- Add **label propagation**: `label_propagation` and
  `grust.algorithms.labelPropagation`, with `maxIterations` and `seed`. A node
  adopts the label carrying the most weight among the nodes with an arc into it,
  so labels flow along the projection's arcs. Updates are asynchronous and
  sequential, in row order or a seeded order per pass, which makes a run
  reproducible; an asynchronous parallel schedule is not. A node keeps its label
  when it is among the heaviest and otherwise takes the smallest of them, which
  guarantees convergence on an undirected projection; a directed run reports
  `converged` honestly. Tests check that every converged run is a fixed point,
  straight from the edge list, over 9,000 random runs.
- Add **closeness** and **harmonic centrality**: `closeness`, `harmonic`,
  `grust.algorithms.closeness` (`useWassermanFaust`) and
  `grust.algorithms.harmonic` (`normalized`, on by default). Closeness is the
  per-component form, `r / Σd` over the `r` nodes reached and zero when none
  are, with the Wasserman-Faust `r / (n-1)` correction on request; harmonic sums
  `1/d` and needs no convention for disconnected graphs. Distances run from the
  node along the projection's arcs, by hop count or by weight; project with the
  opposite orientation for distances to the node. Zero weights are rejected.
  One sweep per node on the caller's rayon pool, bit-identical at any width,
  checked against Floyd-Warshall on every graph of up to five nodes and 600
  random multigraphs of up to forty.
- Add **betweenness centrality**: `betweenness` and
  `grust.algorithms.betweenness`, with `samplingSize`, `seed` and `normalized`.
  Brandes' algorithm, by hop count on an unweighted projection and by Dijkstra
  on a weighted one, in every orientation; undirected sums are halved. Parallel
  edges are distinct shortest paths and each counts. Weighted ties are exact
  `f64` equality, which is exact for integral weights and approximate otherwise,
  and a zero weight is rejected because it makes the path count ill-defined.
  `samplingSize` draws that many sources without replacement and scales the sum
  by `n / samplingSize`; a sample of every node is the exact result bit for bit.
  Sources run on the caller's rayon pool in fixed blocks of 64 merged in block
  order, so scores and charged work are bit-identical at any pool width; memory
  held at once grows with the pool, one workspace per running block. The oracle
  is an all-pairs definition with no traversal in it, checked on every graph of
  up to five nodes and 1,500 random multigraphs, weighted and not, in all three
  orientations.
- Add **Louvain** community detection: `louvain` and `grust.algorithms.louvain`,
  with `resolution`, `maxLevels`, `maxIterations`, `tolerance` and `seed`. It
  works in every orientation: Newman's modularity on an undirected projection,
  Leicht and Newman's directed modularity otherwise, from one formula. Parallel
  edges add their weights; an undirected self-loop counts twice in its node's
  strength, the convention that the two-node test pins. Communities are named by
  their smallest member, as `wcc` names components, and the reported modularity
  is recomputed from the projection rather than accumulated from the moves.
  Moves are applied one at a time in row order or a seeded order, so the result
  is reproducible and independent of the rayon pool; asynchronous parallel moves
  are not. The oracle computes modularity from a dense matrix and the true
  optimum by enumerating every partition: the result is never above the optimum,
  never below its starting point, and equals the optimum on planted cliques.
- Add **triangle count** and **local clustering coefficient**: `triangles`,
  `grust.algorithms.triangleCount` and `grust.algorithms.localClusteringCoefficient`.
  Triangles belong to the simple graph, so parallel edges count once and
  self-loops are ignored, unlike `degree` and `kCore`. A coefficient is null,
  not zero, where it is undefined. `maxDegree` leaves hubs out: such a node
  reports `-1` and triangles through it are counted for no one. The
  degree-ordered forward algorithm finds each triangle once and runs on the
  caller's rayon pool over blocks of equal estimated work; the counts and the
  work charged are identical at any pool width, which a test checks at 1, 2, 3
  and 8 threads. The oracle is the O(n^3) definition over every simple graph on
  six nodes and every four-node multigraph with loops.
- Add **k-core decomposition**, `k_core` and `grust.algorithms.kCore`: bucket
  peeling in O(V + A), returning `coreValue` per node and the graph's
  `degeneracy`. Degree counts parallel edges with multiplicity and ignores
  self-loops. It is defined on undirected graphs and rejects any other
  orientation instead of symmetrizing silently. The test oracle applies the
  definition by brute force to all 1,458 four-node multigraphs with up to two
  edges per pair and to every simple graph on five nodes.
- `grust-algorithm-procedures` gains `run_on_projection(name, &GraphProjection,
  &ValidatedArguments)`, `projection_options(&ValidatedArguments)` and
  `projection_kernel_names()`, behind a new `arrow` feature the facade's `arrow`
  feature forwards. A caller that already holds a projection runs any registered
  kernel by name and receives its typed Arrow results, so an embedding such as
  Nutmeg needs no per-algorithm dispatch and serves a kernel the day it is
  registered. Registration and direct execution read one catalog, and a test
  requires every kernel's Arrow columns to equal its declared outputs.
  `projectionStats` and `estimateCsr` are refused there: they are not kernels
  over a projection.
### Node properties

- Add **node properties**: `NodeProperties`, typed columns read per projected
  node from a `Graph` or from Arrow node batches, row-aligned with a projection
  because they are built against one and hold it. Four kinds — `Number` (f64),
  `Integer` (i64), `Vector` (f32 at a fixed dimension) and `Category`
  (dictionary-encoded strings, for equality filters only). A missing value is an
  error naming the node unless the caller asks for a default or to keep nulls,
  and a column read keeping nulls is reachable only through the `optional_*`
  accessors, `optional_numbers`, `optional_integers` and `optional_categories`.
  Node batches may arrive in any order: values are written at their own row, so
  a caller whose DataFrame is ordered by the engine rather than by projection
  row is not required to sort first. Columns are admitted before they are
  filled and released on drop. See `docs/goals/node-properties-design.md`.
- Add **modularity and conductance**: `community_quality` and
  `grust.algorithms.modularity(communityProperty, resolution)`, scoring a
  partition the caller supplies as a node property. One row per community, led
  by its smallest member. Modularity is the figure Louvain and Leiden optimise,
  by the same formula in every orientation; conductance is the share of a
  community's outgoing weight that leaves it, null where its nodes have no arcs.
  Community ids are any integers, dense or not.
- A registered kernel may declare which of its options name node properties;
  the provider reads them before the kernel runs. `node_property_requests` and
  `run_with_properties` are the embedder path, so a caller that stages its own
  Arrow columns asks which are needed and supplies them.

### Parallel execution

- The catalog kernels take their worker count from the execution
  (`ExecutionContext::with_concurrency`) instead of from whatever rayon pool the
  caller had installed, and charge work through `WorkMeter`. **Behaviour
  change:** a caller that does not ask for concurrency now runs every kernel on
  its own thread and starts no pool; before, a kernel called outside a pool
  spread across every core of the machine. Results are unchanged and remain
  bit-identical at any worker count. Below the shared floor of 16,384 work units
  a kernel stays on one worker whatever was asked for. A budget is now never
  exceeded by work already done: the first accounting layer admitted work after
  performing it and could overshoot by a block per worker.
- `grust-algorithms` gains a default `parallel` feature (rayon). A kernel runs on
  whatever pool the caller installs; without the feature it runs sequentially
  with the same results.
- `ExecutionContext::with_concurrency` permits a kernel to use threads, and
  `ExecutionContext::work_meter` gives one worker a batched share of the work
  budget. An execution that does not ask for threads behaves exactly as before.
- `grust-algorithms` runs `degree`, `pagerank`, `bfs`, `multiSourceBfs`, `wcc`
  and `projectionStats` in parallel when an execution asks for threads, behind
  the default `parallel` feature. Results do not depend on the worker count.

### Changed
- PageRank computes an unweighted projection by pulling into each target rather
  than pushing out of each source when concurrency is requested. The
  distribution is the same and the two paths agree to within a relative 1e-9,
  but the low digits of a score differ from the sequential kernel's, at any
  worker count including one. Evidence that pins PageRank scores to more than
  nine digits should be regenerated rather than compared across this change.

### Execution accounting

- **Memory accounting no longer takes a lock.** `ExecutionContext` holds
  accounted bytes and their high-water mark as atomics and admits a memory
  charge through the same compare-exchange as a work charge, so a byte limit
  stays exact under concurrent charges; a release is one atomic subtraction.
  Only cancellation wakers remain behind the mutex. The reference Cypher
  executor charges memory per copied value, and on the full-path `reduce` query
  this removes 11% at 1,024 nodes and 13% at 4,096 on one laptop; the fused
  `UNWIND` form and the direct kernels do not move. Three behaviours change:
  `usage()` reads its figures in sequence rather than as one snapshot, so exact
  totals should be read after execution (`peak_bytes` is never reported below
  `live_bytes`); the peak can trail a charge by an instant but never misses a
  completed one; and a poisoned lock can no longer fail a memory charge, only
  waker registration. See `docs/lock-free.md`.
- The sequential kernels — `dijkstra`, `shortestPaths`, `bfs`, `dfs`,
  `topologicalSort`, `scc`, `wcc` — and the heap the path kernels share charge
  work through a `WorkMeter` instead of one compare-exchange on the shared
  counter per visited entry. Budgets, cancellation and results are unchanged,
  and the exact-work-charge tests pass as they were. On a million-node,
  ten-million-arc random graph, one laptop, release, no deadline, best of nine,
  per-entry against metered: `dijkstra` 690 ms to 513, `bfs` 312 to 203, `dfs`
  358 to 302, `scc` 682 to 563, `wcc` 310 to 186, with the per-entry figures
  reproduced after the metered run. These are single-host probes, not the
  paired benchmark harness, which has yet to run on this change.

### Projections and results

- **Projections can admit negative weights, by opt-in only.**
  `WeightSelection::SignedProperty` and `GraphProjection::from_signed_topology`
  build a *signed* projection. Only `bellman_ford` runs on one. Every other
  kernel refuses it first thing, because a negative weight would not make them
  fail, it would make them wrong; a catalog test runs all of them on a signed
  projection and demands the refusal, so a kernel added without the guard fails
  it. `projection_options_for(name, args)` gives an embedder the options for a
  named kernel, signed only for `bellmanFord`; the procedure path does the same,
  and signed and unsigned projections never share a cache entry. Nothing is
  signed unless asked for, so no existing caller changes. `WeightSelection`
  gains a variant: code that matches it exhaustively needs the new arm.
- Result tables can key their own rows, so a kernel can answer with node pairs
  (`node1`, `node2`, ...) through the same Arrow and row adapters. A table with
  no rows now yields one empty Arrow batch carrying its schema instead of no
  batch at all.
- `GraphProjection` can build in-arcs with weights and edge slots once per
  projection (crate-internal; label propagation uses them, and the eigenvector,
  Katz and HITS kernels will).
- Add `NodeTable`, a node-aligned result with typed named columns and repeated
  whole-result scalars, with one Arrow adapter and one row adapter. Kernels that
  answer "a value per node" hand it their buffers without copying, so the rest of
  the analytics catalog needs no adapter code of its own.

### Build and CI

- The workspace CI job tests `grust-ladybug` on its own. It had failed on every
  push: LadybugDB's prebuilt library bundles zstd, and the unified all-features
  build linked `zstd-sys` into the same test binary, which `rust-lld` rejects.

## 0.21.0 — Tadpole — 2026-09-18

### Cypher language

- Add `reduce(acc = seed, item IN list | body)`, list comprehensions
  `[item IN list WHERE predicate | projection]` and general
  `any`/`all`/`none`/`single` quantifiers over arbitrary lists and predicates.
  One scoped `Expr` evaluator serves read `RETURN`/`WHERE`/`WITH` and write
  `RETURN`: bindings push an immutable lexical scope, shadowing a row variable
  is a semantic error, and every element charges one work unit so budgets,
  cancellation and deadlines stop a fold between elements. Every read pushdown
  planner declines these forms and stores fall back to the reference executor
  (covered by the Turso differential oracle). The catalog gains `list-reduce`,
  `list-comprehension` and `list-quantifier-predicate` (72 supported of 77).
- **Changed:** write `RETURN` quantifiers are parsed by the general expression
  parser. `CypherReturnTarget::PropertyListPredicate` and
  `CypherReturnListPredicateProjection` are replaced by
  `CypherReturnTarget::Expression(CypherReturnExpression)`. The previously
  admitted `item IN variable.property WHERE item = value` shape keeps its
  exact-equality and NULL-needle results; computed predicates that were
  rejected now evaluate, and a wrong item variable is reported as an unbound
  name instead of an unsupported cardinality.

### Cypher reference executor performance

- Measure serialized size without formatting JSON. `grust-core` gains
  `count_json_bytes` and `json_byte_len`, a byte-counting serializer that mirrors
  `serde_json`'s compact encoding, delegates floats to `serde_json` itself, and
  reports an encoding it does not model so the caller measures through the
  `serde_json` writer instead; a differential test pins the two. Bounded Cypher
  admission and `TypedGraphIndex::serialized_graph_bytes` use it, under the same
  limit and sampled deadline.
- Stop deep-copying relationships and path elements in the Cypher reference
  executor. Bound relationships, variable-length trails and their endpoints,
  shortest-path reconstruction and fixed-path accumulators now hold an owned
  graph's elements by reference and share elements a typed index builds, moving
  rather than copying those. A variable-length trail was copied in full, edge
  properties included, for every result. Candidate rows are a key-sorted vector
  instead of a B-tree, which allocated a full leaf per row; `COUNT`, `SUM` and
  `AVG` fold their arguments as they are evaluated; and `UNWIND` moves the row
  into its last element. Logical copy charges are unchanged. On a 200,000-node
  ring, `[:KNOWS*1..3]` went from 1.1 s to 0.54 s and an eight-element `UNWIND`
  with `sum` from 1.3 s to 0.57 s (single release-mode runs).
- Add `PathValue::from_graph_elements`, which builds a path value from borrowed
  nodes and relationships that are not held in slices.
- Bind matched nodes of an owned graph by reference in the Cypher reference
  executor. A `MATCH` start candidate was deep-copied into the candidate list
  and again into the row, and every matched neighbour was deep-copied once; rows
  now carry `&Node` into the graph they read, and only nodes a typed index
  builds on demand are shared copies. Logical copy charges are unchanged, so
  budgets admit and reject exactly the same queries. Scalar function dispatch
  also stops allocating a lowercased name per evaluated call. On a 200,000-node
  graph a filtered scan went from 282 ms to 145 ms and a one-hop match from
  510 ms to 241 ms (single release-mode runs, not a benchmark suite).
- Sample the deadline in bounded Cypher reads. Admission measured a graph's
  serialized size through a writer that read the clock on every `serde_json`
  token, and the thread-local read budget read it on every charge and every
  expression checkpoint. The writer now reads it on the first write and once per
  64 KiB; the budget reads it on the first tick and every 1024 ticks, and an
  observed expiry stays observed. Work and byte limits are never sampled. On a
  200,000-node scan this took a bounded `count(*)` from 937 ms to 488 ms against
  282 ms unbounded, on a host with a cheap clock.

### Execution accounting

- Full-path procedure results cost less to consume from Cypher. A streaming
  `CALL` deep-copied every yielded value into each row, so a path's `nodeIds`
  list was cloned once per path; a yielded value is now borrowed from its batch
  and still charged as a full copy. The shortest-path output cursor and its
  parent walk admit work per path, or per 1024 steps, instead of once per entry;
  the streaming `SUM` state folds without rebuilding a slice per value; binding
  forms admit their elements in blocks of 1024; and leaf expressions no longer
  checkpoint the deadline, which their enclosing expression has already done.
  Totals charged are unchanged, and a budget, cancellation or deadline still
  stops a fold between blocks. On a 1024-node chain (524,800 path entries) the
  `UNWIND range(...)` full-path aggregate went from 88 ms to 58 ms and the
  equivalent `reduce` form from 298 ms to 254 ms; `reduce` remains about four
  times the `UNWIND` form because each element still pays general expression
  evaluation and per-value byte accounting.
- `ExecutionContext::charge_cumulative_memory` and `MemoryAccount::charge`, the
  per-copied-row charges, sample the deadline as `charge_work` does instead of
  reading the clock for every charge. The byte limit and cancellation remain
  exact, and `reserve` and `checkpoint` still read the clock. Together these took
  a bounded 200,000-node scan from 340 ms to 237 ms (937 ms before this series;
  101 ms unbounded).
- Sample the deadline on work charges instead of reading the clock for every
  unit. Kernels charge once per visited entry, so a per-unit `Instant::now()`
  costs more than the work it guards wherever the clocksource is paravirtualised:
  on such a host it was about 83% of a full-path Cypher query, which now runs
  8.4x faster with identical results. Expiry is observed within 1024 charges;
  `checkpoint` still reads the clock exactly, and cancellation and budget limits
  are never sampled.
- Charge cooperative work units and observe cancellation without taking the
  execution mutex: `ExecutionContext` now holds `work_units` and `cancelled` as
  atomics, admitting each charge through a compare-exchange that recomputes the
  budget against the value it replaces. Exact budget enforcement, per-unit
  granularity and cancellation visibility are unchanged; memory reservations,
  peak accounting and wakers still hold the lock. Profiling attributed 72.8% of
  full-path Dijkstra kernel time on a 16384-node chain to the previous
  lock-per-unit accounting.

### Arrow and DataFusion

- Validate row-to-Arrow conversion with borrowed identity membership instead of
  constructing discarded adjacency, and copy string properties directly into
  Arrow buffers without temporary owned String clones.
- Add automatic Cypher routing through `grust_datafusion::cypher::RoutedGraph`:
  one graph captured as a typed index and an Arrow snapshot, one bounded-read
  admission per query, and DataFusion execution for single-node scan plans
  whose every physical operator charges candidate work and intermediate bytes
  against the caller's `ReadQueryPolicy`. Relationship joins, unsupported
  shapes, small graphs and plans over a limit stay on the reference executor;
  explain reports the chosen route and why DataFusion was declined.
- Add `run_prepared_read_query_indexed`, so a declined route keeps the original
  admission and deadline instead of re-preparing the query.
- Split large single-batch Arrow tables into contiguous zero-copy partitions.
  Upstream round-robin repartitioning charged every queued slice the full size
  of its shared parent buffers, which intermittently exhausted a 256 MiB pool on
  a one-million-node scan with nothing copied.

### Ladybug (internal adapter)

- `grust-ladybug` bulk loads `COPY` from a temporary CSV instead of inserting
  row by row, and skip the read-back of an empty table. A caller that loads one
  fresh graph in disjoint chunks can call
  `LadybugGraphStore::set_bulk_load_trusts_fresh_rows(true)` to skip the per-chunk
  scan of stored keys, which was quadratic in the chunk count; node ids copied in
  that mode are remembered so an edge batch carrying its endpoints does not
  collide. The mode is off by default, and a key the store already held is then
  the caller's error. `lbug` moves to 0.20.4. The crate remains `publish = false`.
- Add `LadybugConfig::max_db_bytes`. Ladybug reserves its maximum database
  size (8 TiB by default) as virtual address space per open database, so one
  x86-64 Linux process can hold only about fifteen at once. `grust-ladybug`
  unit tests now cap each database at 16 GiB, as Ladybug's own tests do;
  parallel test threads previously failed intermittently with `Mmap ... failed`.

## 0.20.0 — Brine — 2026-09-14

- Preserve algorithm-result admission through independently retained raw Arrow
  batches and nested array children. Shared array ownership covers payload and
  validity buffers without copying payload bytes; metadata is revalidated.

- Retain application-owned tokens through native Arrow buffers, slices and C
  Data export using safe shared Bytes ownership across Arrow 55/58/59.
- Admit snapshot relationship-ordinal payload and construction work before
  allocation, retaining reservations with emitted buffers. Combined input-policy
  capture preserves the prepared request deadline and exact serialized limits.
- grust-turso no longer creates `<prefix>_edges_from_idx`, and bootstrap
  drops it from existing stores. The edge primary key
  `(from_id, label, to_id, identity_key)` leads with `from_id`, and Turso's
  planner already answered every source lookup and traversal hop from that
  key, so the index only cost a write per edge. Query plans and results are
  unchanged. Other SQL dialects keep the index (`GraphSqlDialect::
  edge_source_index`, default `true`). With the bulk_load example on a
  4-core host, 1M edges: MVCC 12.7k -> 15.9k edges/s, WAL 43.6k -> 51.5k.
- MVCC loads end in a `TRUNCATE` checkpoint inside `put_graph`, as WAL loads
  already did, so a load returns durable in the database file with the MVCC
  in-memory store drained.
- Optional `mimalloc` feature on grust-turso: Turso's own default allocator,
  installed as the binary's global allocator (MVCC loads about 9% faster).

## 0.19.0 — Mantis — 2026-09-14

- Add shared-context admission before portable DataFusion result decoding,
  charging cumulative logical copy bytes for the actual Arrow slice before
  allocating row values and strings. Full operator accounting remains separate.

- LanceDB bulk loads build or update merge-key indexes; concurrent single-row
  writes share queued commits with last-key-wins batching. Leadership remains
  owned through cancellation before a handoff receiver polls. Abandoned
  in-flight batches report uncertain durability explicitly.
- Periodic fragment compaction, write-time read-snapshot invalidation and
  bounded connection caches reduce avoidable retained state. Performance
  qualification remains separate from correctness tests.

## 0.18.0 — Ostracod — 2026-09-14

- Admit native Arrow graph row counts and exact serialized bytes through the
  shared prepared-read policy, preserving its original deadline. Optional
  DataFusion input-policy capture caches the measured size; ordinary capture
  explicitly leaves it unknown. This does not replace execution accounting.

- Add a borrowed serialization view of native Arrow graph tables on Arrow
  55/58/59. It preserves the core graph wire format without allocating row graphs
  or copying property values, and composes with bounded output/counting writers.

- Expose exact native snapshot row/batch counts and added relationship-ordinal
  payload bytes for routing preparation, without scanning providers or exporting
  graph rows. Unknown selectivity and memory costs are not guessed.

- Share bounded Cypher request preparation, immutable parameter admission,
  graph/index size checks and output checks through `PreparedReadRequest`.
  The reference executor uses the same checks and original absolute deadline;
  oversized parameters now fail before graph inspection. Route-specific work
  and intermediate budgets remain separate requirements.

- Add runtime-independent cancellation subscriptions to the shared execution
  context, waking all live waiters without retaining dropped subscriptions.
- Add DataFusion future lifetime control and explicit Cypher execution with a
  shared cancellation/deadline context. Pending operations release their owned
  streams and reservations on cancellation; full read-policy accounting and
  automatic routing remain under development. Controlled Arrow streams retain
  this context through SQL/ADBC consumption without copying batches.

## 0.17.0 — Isopod — 2026-09-14

- Preserve exact Int64 ordering in portable Cypher comparisons, including
  adjacent values beyond Float64 integer precision.
- Add optional DataFusion 55 lowering of typed Cypher scalar predicates and
  single-node scans, scalar parameters, inline property maps, identity,
  count/grouping, integer/string extrema, ordering and pagination. Typed planner
  decisions preserve unsupported outcomes separately from semantic errors.
  Scalar and aggregate compilers share a typed binding resolver for composable
  multi-binding inputs. Immutable provider pairs add snapshot-scoped physical
  relationship ordinals while sharing existing Arrow buffers. A composable
  directed endpoint-join operator retains typed bindings and edge multiplicity.
  Parsed incoming/outgoing single-hop patterns share RETURN and inline-property
  predicate planning with scans, including parameterized edge and endpoint maps.
  Undirected one-hop patterns retain both edge orientations and emit loops once.
  Repeated endpoints use a single node join and explicit self-loop constraint.
  Anonymous node/relationship elements receive collision-free private bindings.
  A common snapshot planner reports the selected shape and unsupported reasons.
  Native scalar results convert to portable Cypher rows with exact integer/null
  semantics and explicit rejection of unsupported Arrow types. Incremental
  collection enforces cumulative rows and serialized JSON output bytes.
  An explicit snapshot execution entrypoint connects Cypher text parsing, typed
  planning and output-bounded collection without fallback after errors.
  Combining facade `cypher` and `datafusion` features enables the bridge.
  Composable trail joins preserve shared nodes, exclude physical edge reuse
  across all parts and reject mixed snapshots. Parsed fixed-length paths now
  reuse these operators with shared predicates, grouping and RETURN planning.
  This is an explicit planning API; automatic routing,
  bounded Cypher policy integration and broader query support remain pending.

## 0.16.0 — Amphipod — 2026-09-14

- Add degree analytics through the direct Rust projection API, native Arrow
  result cursor and ordinary `grust.algorithms.degree` procedure. Exact counts
  include parallel and zero-weight arcs; optional weighted strength retains the
  projection's finite nonnegative-weight contract. Isolates and all projection
  orientations are supported, with undirected loops counted once.
- Degree kernels use existing CSR offsets and bounded work-admission chunks;
  counts take O(V), weighted strength O(V + A). Result storage retains memory
  admission, successful work charges remain exact, and nonfinite strength sums
  fail explicitly. Independent multigraph oracles and prepared-projection
  benchmarks cover the new surface.

## 0.15.1 — Copepod — 2026-09-14

- Candidate rows in the portable Cypher executor share immutable node and edge
  bindings instead of repeatedly cloning their property maps. Projected values
  remain owned, relationship identity and row order are preserved, and logical
  full-element copy charges remain conservative. Source-pinned relational
  profiles retain exact oracle checks and before/after resource evidence.

- Cypher `sum()` now returns integer zero for empty or null-only input in both
  materialized and streaming aggregation. `avg()` remains null for those inputs;
  empty grouped input still produces no groups. The correction includes DISTINCT
  and indexed-read regression coverage.

## 0.15.0 — Gooseneck — 2026-09-14

- Shared Arrow pipelines now serve LanceDB, Sail, Ladybug and the optional
  QueryGraph Memory Sail adapter. Additive Arrow 55/58/59 features use shared
  implementations with native SDK types. Standard readers support bounded
  zero-copy row slicing, explicit column projection, multi-batch IPC, schema
  validation and optional C Stream export through upstream Arrow.
- `ArrowTable` preserves arbitrary native types, metadata and batch boundaries.
  `ArrowGraphTables` validates graph identities across batches without building
  property rows or adjacency. Existing `ArrowGraph` construction now validates
  columns directly; its single-batch file-format API remains available.
- Optional ADBC integration binds standard Arrow 59 readers to caller-owned
  statements using upstream ingestion options. Driver errors and unknown row
  counts remain intact. Driver lifecycle, transactions and capabilities stay
  with ADBC; ingestion modes do not imply graph upserts.
- Added optional `grust-datafusion`, a shared DataFusion 55 foundation over
  native Arrow 59 tables and graph catalogs. Upstream providers retain pushdown;
  read-only SQL returns native streams with explicit working-memory and spill
  settings. A caller-driven blocking reader composes results with ADBC. This
  does not change Cypher lowering or older database SDK execution engines.
- LanceDB and Sail accept native readers for graph bulk loads. LanceDB shares
  storage batch encoders and preserves input arrays through merge insertion;
  Sail stages columnar input without whole-stream Graph materialization and
  preserves identity arrays while normalizing its SQL property representation.
  Stream loads have batch-local validation and can retain prior committed
  batches after a later error. Sail's graph IPC convenience loader now follows
  that streaming contract and preserves explicit empty edge IDs.
- Ladybug exposes native reader registration and streaming batch callbacks;
  its persisted bulk COPY path uses shared Arrow construction. QueryGraph
  Memory retains its strict pre-decode checks and byte budgets while sharing
  IPC encoding/decoding.
- Added Arrow/ADBC architecture documentation, a maintained performance and
  compatibility goal, and reproducible native/IPC and graph-validation
  Criterion workloads. These are distinct from active source-pinned backend
  benchmark runs.

## 0.14.0 — Acorn — 2026-09-14

- LanceDB snapshot invalidation tracks table generations as well as versions,
  so an older in-flight build cannot make recreated tables serve stale rows.

- `grust-lancedb` answers anchored reads (`get_node`, `get_nodes`,
  `get_edges`, `traverse`, `traverse_ids`) from a resident read snapshot
  instead of a filtered scan of the whole table per call. LanceDB keeps no
  index on `from_id`/`to_id`, so each traversal step scanned the edge table
  once per frontier node and the node table twice. The snapshot mirrors both
  universal tables once per pair of table versions (node ids interned to
  `u32`, out- and in-adjacency in scan order, props and edge ids kept as the
  scanned Arrow strings) and is used only while both tables still report
  the versions it was read at, so writes through this or another connection
  are seen on the next read, as before. It is built on the second read at
  unchanged versions, so a caller alternating writes and reads keeps the
  direct scans. Results and their order are unchanged. `traverse_ids` is now
  overridden and skips building nodes it would discard. The direct scans
  remain behind `LanceDbGraphStore::with_read_snapshot(false)`.
  On web-Google (875,713 nodes, 5,105,039 edges) a one-hop `traverse_ids`
  took 0.373 s over the direct scans and 94 µs over the snapshot, which
  builds in 1.8 s. Extrapolating the direct-scan call time over the strain
  benchmark's A2 BFS (600,493 calls) gives about 62 hours; the snapshot run
  measured 57 s. Example: `anchored_reads`.

- `TursoGraphStore::put_graph` binds rows to prepared multi-row upserts
  instead of rendering each batch as SQL text. Each statement shape is
  parsed once per load rather than once per batch, and only one batch of
  bound values is alive at a time; the old path held the SQL text of the
  whole load in memory before executing any of it. The statements are the
  same `INSERT ... ON CONFLICT DO UPDATE` upserts as `upsert_nodes_sql` /
  `upsert_edges_sql`, so a repeated key still keeps its last row. A new test
  loads a graph that rewrites nodes and edges (missing, empty, plain and
  prefix-like edge ids) through both paths, in WAL and MVCC mode and with
  batch sizes 2 and 500, and compares the stored rows including
  `identity_key`.
- Ordinary, non-synced connections set `PRAGMA cache_size` to 1 GiB
  (`PAGE_CACHE_KIB`); synced connections retain their existing configuration.
  The engine's native default is 2,000 pages (about 8 MB), which a load
  outgrows within its first million edges; after that every insert into the
  edge key, the two edge indexes and the node-key foreign-key probes reads
  pages. The cache fills lazily, so a small store holds only its own pages.
- Measured with the new `bulk_load` example on a shared 4-core host, fed as
  the adversarial-graph harness feeds it (vertices first, then edges in CSR
  order, 5M-edge `put_graph` calls):
  2M edges 22.5k -> 42.5k edges/s; 10M edges 21.5k -> 35.8k edges/s;
  30M edges 31.6k edges/s overall, 37.9k falling to 28.3k per 5M-edge batch, levelling off
  rather than collapsing. SNAP cit-Patents (3,774,768 nodes, 16,518,948
  edges) loads in 550 s, 32.6k edges/s; the strain benchmark measured 811 s
  for it before this change, on a different host.
- Unchanged: the schema and its indexes, the query plans of anchored edge
  lookups and two-hop traversals, WAL as the default journal mode, MVCC's
  grouped commits (`MVCC_LOAD_COMMIT_STATEMENTS`), foreign-key checks, and
  the edge identity encoding and its migration.

- Indexed Cypher materializes a full graph for `CALL` only when the registered
  provider declares `GraphRequirement::LocalSnapshot`. Graph-free procedures
  such as `tvf.range` and `db.procedures` retain the compact source in both
  streaming and materializing query pipelines.

- Cypher over `grust-memory` reads the store in place instead of a copy of
  it. `MemoryGraphStore::indexed_snapshot` shares the store's frozen storage
  (copy-on-write: a write copies the store only while an older snapshot is
  still held) and adds three `u32` permutations plus the typed adjacency;
  nodes and edges are built on demand, one at a time, when a query examines
  them. `TypedGraphIndex` now reads its graph through the new
  `GraphSnapshotSource` trait (`TypedGraphIndex::from_source`, with slot
  accessors `node`, `edge`, `node_label`, `node_property`, `edge_props`, ...);
  `TypedGraphIndex::new(Arc<Graph>)` is unchanged, and `graph()` still returns
  a `&Graph`, materializing one on first use for a borrowed source. The
  reference executor behind `execute_read_query_indexed` walks the index
  instead of `index.graph()`, visiting candidates in the same order and
  charging the same budget, so results, refusals and error messages are
  unchanged; bounded indexed reads take node and edge counts and the
  serialized size from the index. With 10 million untyped edges the store
  plus the Cypher read path hold 83 bytes per edge instead of 213 (the read
  path 35 instead of 165), and the benchmark's anchored reads run in
  milliseconds instead of seconds (`crates/grust-cypher/examples/memory_footprint.rs`, which now also
  builds the snapshot and answers out-degree and two-hop reads).

- `grust-memory` stores each edge once: node ids and labels are interned as
  `u32` handles, an edge is a 16-byte record listed by slot in `u32` adjacency
  lists and found by key through a hash index, and edge ids and properties
  live out of line, costing nothing when absent. A node's `id` property is
  kept implicitly when it equals the node id. Loading 10 million untyped edges
  over 500,000 nodes grows RSS by 48 bytes per edge instead of 694
  (`crates/grust-cypher/examples/memory_footprint.rs`). Edge identity is unchanged: `(from, label, to, id)`
  keys parallel edges with distinct ids, and reads return nodes and edges in
  the same id and edge-key order as before. Adding a native constraint no
  longer clones the whole store to validate it.

- Turso under MVCC loads in groups: `put_graph` commits every
  `MVCC_LOAD_COMMIT_STATEMENTS` (20) batches as its own `BEGIN CONCURRENT`
  transaction instead of one transaction around the whole load. MVCC keeps an
  open transaction's row versions in memory until commit and retried the
  entire load on a conflict; the adversarial-graph strain benchmark measured
  about 1,500 edges/s that way, too slow to attempt cit-Patents inside its
  two-hour budget. Under MVCC a load is no longer all-or-nothing: a failure
  leaves the groups committed before it. WAL mode is unchanged.

- Turso keeps parallel edges. The universal edge table's key gains an
  identity column through a new `GraphSqlDialect::edge_identity_column` hook
  (default none, so PostgreSQL's schema is unchanged); Turso sets `identity_key`,
  an encoded optional ID, and upserts on (from_id, label, to_id, identity_key).
  Missing and empty IDs remain distinct; migrated stored IDs retain their
  update identity. Both the old endpoint-only schema and the unreleased raw
  `id_key` schema are rebuilt transactionally.
  Edges with distinct ids between the same endpoints are all kept, as
  grust-memory and LanceDB already did; an edge without an id still replaces
  the earlier one; re-putting an id updates it in place. A database created
  with the old (from_id, label, to_id) key is rebuilt once at bootstrap, in
  one transaction, keeping every row. The adversarial-graph strain benchmark
  found the gap: on sx-stackoverflow, a temporal multigraph, Turso merged
  27 million parallel interactions and answered hub degrees wrong.

- Added generalized analytics infrastructure: Arrow graph interchange from the
  pinned handoff is available through the optional facade `arrow` feature;
  `grust-procedures` adds immutable registration and shared resource contracts.
  The Cypher source now resolves CALL through that registry, including external
  providers and correlated CALL subqueries. Bounded reads separate catalog/table
  admission from read-procedure permission, and provider allocations share the
  existing read budget. Explicit local snapshot capabilities preserve graph,
  revision and principal identity through prepared execution.
- Added reusable BFS, Dijkstra, full shortest paths, WCC, iterative SCC and
  weighted PageRank kernels, native multi-batch Arrow projection and typed Arrow
  results. The optional facade `algorithms` feature exposes kernels and registry
  adapters; all six run through ordinary Cypher with checked configurations.
  The same extension contracts also expose DFS, multi-source BFS, topological
  order with cycle witnesses, projection statistics and scoped CSR sizing.
  Query-scoped projection reuse includes graph, revision, principal and options;
  prepared explanations and `db.procedures` use pinned registry metadata.
- Added incremental CALL/YIELD/filter/WITH/UNWIND consumption and ungrouped
  COUNT/SUM/AVG, live intermediate admission and LIMIT propagation. Array indexing
  borrows bound arrays instead of copying the whole array per element. Generic
  typed-array aggregate fusion consumes actual path entries. Local Memory and
  private Turso snapshots are tested with the same prepared bounded plan; old
  captures survive writes. Full-chain direct and ordinary Cypher receipts retain
  their exact resource and timing boundaries in `benchmarks/algorithms`.
- Integrated the pending backend batch configuration: Surreal and Helix HTTP
  distinguish bulk loads from incremental writes. LanceDB reuses table handles
  with latest-read consistency and serializes lookup against local recreation.
  This preserves cross-connection writes and prevents stale cache publication.
- Fixed Turso's optional sync constructor to initialize its snapshot cache and
  retire the cache before a pull can mutate local data, including failed or
  cancelled pulls. Existing immutable snapshots remain valid.

- Surreal: an edge written without its endpoints' tables in hand (a single
  `put_edge`, an `UpsertEdge` mutation) relates the record a node read by
  that ID would find, `RELATE (SELECT VALUE id FROM type::record(t1, id),
  …)->…`, and its idempotent delete matches the same candidates. The
  endpoint was guessed from the ID's prefix, so a plain ID such as `160`
  went to `record:160`, a record no node occupied, while the node was
  `v:160`: the adversarial-graph hot-node writes of 2026-09-11 put 3,200
  edges there, readable only because edge reads also search `record`. A
  missing endpoint now relates nothing rather than a phantom.

- Surreal HTTP: the store signs in once (`/signin`) and sends the session
  token as a bearer on every request, refreshing it once on a 401. Basic
  auth on `/sql` was a sign-in per request, and the server hashes the
  password each time: about 50 ms of server CPU per request on v3.2.4
  against 2 ms under a token, measured end to end on the same query, so a
  two-hop walk of a thousand neighbour reads was 45 s of server time
  before any query ran.

- Surreal: an edge read filtered by endpoint is `in IN [type::record(t, id),
  …]` (and `out IN […]`) over the candidate tables a node read by that ID
  searches, which the planner answers from the relation's endpoint indexes
  as a union of index scans; it was `meta::id(in) = …`, a function of the
  field and so a scan of the whole relation per frontier node, which made
  the adversarial-graph two-hop walks on ego-Facebook minutes of server
  CPU (A2 up to 16 min at 88k edges). Relation tables carry a second
  index over `out` for incoming-edge reads. The Rust postfilter on the
  full key stays; an edge whose endpoint this adapter could read by ID is
  an edge it finds.
- Helix SDK: the store keeps the server's handle for every node it
  created (`add_n` answers `{"created_i": [{"$id": N}]}`) and writes an
  edge between two such nodes by their handles, and reads a node or
  starts a traversal at one by its handle. Against the standalone SDK3
  server a `nodes_where id = …` lookup is a scan of every node whatever
  equality index exists (28 ms at 4,039 nodes: a 500-edge batch 43 s,
  88k edges past two hours); by handle the same batch is 0.3 s. An
  endpoint the store did not create is still looked up by `id`; the
  handles go with `clear`.

- Surreal: every relation table carries an index over `(in, out)`, defined
  with the table in the schema and in the `DEFINE TABLE IF NOT EXISTS` path
  a relate batch opens with. The idempotent `RELATE` deletes the edge's
  earlier copy by its endpoints first, and without the index that delete
  was a table scan: a load of E edges cost O(E²), and the adversarial-graph
  ladders saw every full-tier Surreal HTTP load die at ~300 s in the HTTP
  client's minute-long request timeout ("failed to POST SurrealQL: error
  sending request"), on every host, 2026-09-10. Edge reads by endpoint use
  the same index.
- Surreal: `SurrealConfig.request_timeout` bounds one HTTP request (default
  the minute it always was); the SDK transport ignores it.
- Surreal: node reads by ID (`get_node`, `get_nodes`, and every traversal
  step) select the candidate records directly (`FROM type::record(t, id),
  …`) instead of scanning the candidate tables under an OR-chain of
  `id = …`. SurrealDB parses the chain recursively and refuses it past a few
  hundred terms ("Parse error: Exceeded expression recursion depth limit",
  v3.2.4), which a traversal frontier reaches on any graph beyond a toy:
  the ladders' Surreal SDK A1 and A2 at 4,039 nodes. `get_nodes` sends one
  statement per `batch_size` IDs.
- Helix: the SDK adapter's errors carry the client's own text ("Got Error
  from server: …", the transport error) instead of a fixed phrase, so a
  server that refuses the SDK's wire format can be told from one that is
  down. The `helix-db` 3.0.0 client posts a nested query AST to `/v2/query`;
  the enterprise-dev registry image serves `/v1/query` only and answers
  every SDK request with 400 "missing field `queries`", which is what
  "Helix SDK replace/drop failed" was hiding.

- LSQB matrix: a Turso observation worker no longer reloads the CSVs; the
  coordinator loads the dataset once into a file-backed store and each
  worker copies that file into a private path, opens the copy and builds its
  resident index before READY, under the new lifecycle strategy
  `per-observation-worker-copy` (process exit still proves recovery). At
  SF0.1 that is a 0.24 s copy of a 553 MB file plus about 5 s of read-back
  and index build in place of a 67 s reload per observation. The validator
  expects the new strategy for Turso; the site verifier admits either
  process-owned strategy so earlier receipts still verify.
- LSQB matrix: a durable store with a resident index takes the proven
  `count-factorized` plan over that index before its own scalar SQL count,
  for Turso and PostgreSQL alike; `sql-count` stays the route, under its own
  class, only for a count the proof does not admit. Measured at SF0.1 on
  Turso: 260 s (q1) and 14.7 s (q4) through the store's `SELECT COUNT(*)`
  against 66 ms and 165 ms for the same plan over the index. All 22 pinned
  cases now register as resident-index entries for both stores.
- Fix the publication receipt step under macOS bash 3.2: an empty
  `create_arguments` array (no `RESUME_FROM`) was an unbound-variable error
  after all 24 cells had run. The SF0.1 run at `68d1b09` was receipted by
  hand with the same arguments.
- LSQB matrix resume mode: `RESUME_FROM=<prior OUTPUT_DIR>` makes a
  publication run copy in every cell of a prior publication run whose
  outputs verify against the prior receipt's hashes and were produced at the
  same revision, images and cell timeout as a valid cell, and execute only
  the rest. The receipt's new `reused_cells` list names each reused cell with
  the prior directory, receipt digest and Compose project; the publication
  validator and the site verifier check reused cells' watchdog records
  against it and reject unexplained foreign records, reused failures, and a
  run that executed nothing.
- LSQB matrix: a durable store with a resident typed index built inside its
  worker's load interval declares the distinct execution class
  `backend-resident-index-rust-count` for queries whose structural proof admits
  `count-factorized` and whose dialect renders no scalar SQL count. Turso is
  the first such store (`TursoGraphStore::indexed_snapshot`): its worker reads
  the loaded store back, builds the `TypedGraphIndex`, and runs the same
  non-materializing count plans Memory runs, under the new class, with the
  registry-bound not-materialized row exemption. The plan registry, the
  publication validator and the site verifier's per-backend class allowlist
  admit the class; the row-source and materialize routes remain for every
  query without such a proof.
- Ladybug loads through registered Arrow tables and `COPY … FROM (MATCH …)`
  (the crate's `arrow` feature, now on by default): rows grouped per table,
  new ids and `(from, to)` pairs copied, existing ones merged as before, last
  row per key wins within a load, and tables are resolved once per distinct
  label rather than once per row. A traversal step is one query per
  relationship table (`MATCH (a)-[r]->(b) WHERE a.id = $id`) instead of one
  point lookup per neighbour, `traverse_ids` returns ids only, and
  `LadybugConfig::buffer_pool_bytes` caps the engine's host-sized buffer pool,
  and `concurrent_writes` turns on the engine's multi-writer mode and lets
  writers run on their own connections instead of queueing on one lock.
- Turso and PostgreSQL keep a resident typed snapshot:
  `TursoGraphStore::indexed_snapshot` and `PostgresGraphStore::indexed_snapshot`
  build a `TypedGraphIndex` from a full read of the store under the
  connection gate, share it until any command that can change the store
  runs, and serve the indexed Cypher entrypoints; `GraphStore` reads are
  unchanged. In the LSQB matrix a PostgreSQL observation worker builds its
  index from a read-back of the once-loaded service before READY and takes
  the same `backend-resident-index-rust-count` route as Turso; the registry,
  validator and site verifier admit the class for both.
- A cell whose backend cannot prove quiescence after an unacknowledged worker
  exit now ends as an explicit error result instead of aborting the matrix:
  the terminal observation is recorded, the lifecycle declares the
  termination (`backend.quiescence-unproven`), short queries are explicit
  errors, and the receipt shows the failure. FalkorDB q9 at SF0.1 is the
  first such case.
- Reserve up to five seconds (was one) of the coordinator deadline for
  FalkorDB's native TIMEOUT acknowledgement; at SF0.1 q9 overshot the
  one-second reserve and the unacknowledged kill aborted the cell.
- Reserve up to five seconds (was one) of the coordinator deadline for
  FalkorDB's native TIMEOUT acknowledgement; at SF0.1 q9 overshot the
  one-second reserve and the unacknowledged kill aborted the cell.
- Serve Memory `traverse` and endpoint-anchored `get_edges` from the cached
  typed snapshot when one exists: a load into an empty store builds it, any
  write invalidates it, and reads without one keep the existing edge-map walk,
  so point-write workloads never rebuild an index inside a read. Results and
  order are unchanged except that `Direction::Both` lists outgoing before
  incoming neighbours. `TypedGraphIndex` measures its serialized size on first
  use instead of at construction and exposes `relationship_types()`.
- Add `GraphStore::traverse_ids`, the ids `traverse` would return in the same
  order, with a default through `traverse` so every store keeps working; the
  Memory store answers it from the snapshot without cloning nodes.
- Turso `put_graph` loads every batch inside one transaction: one durable
  commit for the whole graph instead of one per batch, and the load is atomic.
- Make the host preflight's aggregate-CPU limit an explicit, recorded
  parameter (default two cores, at most four); the busy-process rule is
  unchanged and legacy records without the field are still held to two cores.
- Harden benchmark cancellation: latch SIGINT/SIGTERM through child creation,
  reap owned process groups, revalidate exact container identity during cleanup,
  and report cleanup failures as errors. Allow an explicit longer logger grace
  so nested container cleanup can finish before escalation.
- Record worker-selected LSQB execution plans in new observations and incremental
  journals, including timeouts. Keep missing-plan evidence explicitly legacy,
  validate plan/class compatibility, and prevent mixed-plan timing aggregation;
  preserve the frozen Neo4j and upstream bundles without backfilling metadata.
- Require and hash-bind passing startup host screens for newly opted-in canonical
  matrix bundles, validating them on receipt creation and verification. Preserve
  historical layouts and distinguish startup-only evidence from ongoing host
  isolation in performance summaries.
- Audit historical Surreal and Helix SDK cohorts against their original,
  content-addressed manifest instead of the changing current manifest. Keep
  source/digest pins and frozen audit outputs unchanged; missing or altered
  historical contract bytes fail closed without fallback.
- Add an immutable typed snapshot index and a separate indexed read entrypoint
  with exact factorized `count(*)` for proven fixed-length pattern forests and
  unequal-endpoint two-hop wedges with a differently typed outgoing leaf.
  Independent optional leaves retain null padding and bag multiplicity through
  a restricted plain `WITH`, without moving optional predicates into mandatory filters.
  Preserve edge multiplicity, self-loop handling, scalar limits and active read
  budgets; unsupported plans retain the existing executor. Memory caches indexed
  snapshots across reads and invalidates them on writes; the bounded indexed API
  checks cached exact graph size without serializing it on every query.
- Extend indexed count algebra to weighted tag intersections and optional-null
  tag/wedge anti-joins, preserving parallel edges and witness-existence semantics.
  Add nonnull node/edge counts, zero-hop identity paths, bounded range counts,
  null/constant-string probes and scalar unions without matching-row buffers.
  Borrow scalar predicates without copying incompatible complex JSON properties;
  retain numeric/temporal equality, range ceilings and cumulative work limits.
- Count proven directed four-cycles with grouped multiplicities and adaptive
  adjacency probes, and symmetric location triangles with sparse path weights
  and oriented intersections. Do not assume functional creator/location edges.
- Narrow cycle role candidates using required labels from any node mention;
  keep every predicate, unlabeled full scans and cumulative resource accounting.
- Replace repeated wedge anti-neighbor probes with exact weighted support
  triangles, sharing degree-oriented topology with location triangles. Preserve
  asymmetric role filters and witness existence, with accounted O(V + M) scratch.
  Compact stored support multiplicities to checked `u32` values while retaining
  wide count arithmetic. Precharge small fixed-cost anti-wedge mask chunks,
  preserving cumulative work totals and deadline checkpoints.
- Sort shared support targets by explicit simple-degree/stable-vertex-slot rank
  and intersect only the safe strict suffix. Translate triangle callbacks back
  to original active-domain ordinals, preserving weighted location-triangle and
  wedge anti-join semantics. Rank construction adds charged O(V log V) work and
  two V-entry `u32` maps, one retained; support scratch remains O(V + M), with V
  active vertices and M distinct non-loop support pairs.
- Prepare wedge role masks from required-label candidates; initialize
  unconditional unlabeled roles directly without per-vertex predicate checks.
  Preserve overlapping roles, every label conjunct and full-size scratch charges.
- Reuse borrowed label candidates for wedge leaf/center scans and mandatory
  forest branch combination. Avoid revisiting unrelated zero-weight vertices
  without allocating candidate lists or repeating label lookups. Unlabeled
  roles retain full scans; predicates, optional padding and full-size scratch
  accounting remain unchanged.
- Prefilter property-bearing forest roles with at least two mandatory incident
  atoms using necessary typed-adjacency existence checks. Charge each actual
  lookup, keep original predicates for survivors, and exclude optional edges;
  no candidate allocation or neighbor scan is added. Dense roles can pay extra
  lookup overhead, so this is not a general selectivity or performance guarantee.
- Add copyable borrowed typed-adjacency views that resolve a relationship type
  once while preserving dense/sparse lookup, physical multiplicities and snapshot
  lifetime. Cache views for enabled mandatory-adjacency prefilters, charging
  preparation storage, one-time type resolution and individual row probes;
  disabled/empty roles retain their allocation-free path.
- Borrow sparse typed source lists to narrow enabled mandatory forest roles
  when strictly shorter than the current label/full-domain candidates. Preserve
  all predicates, row probes, bag multiplicities and full-domain accounting;
  dense/undirected atoms do not supply seeds, and no candidate lists are copied.
- Prepay mandatory forest branch scans in borrowed chunks of 256 physical
  adjacency slots. Successful work totals, loop/parallel-edge semantics and
  per-predicate charges remain exact; tight budgets can refuse a whole chunk
  before its partially affordable prefix. Optional execution is unchanged.
- Count non-anti wedges in one grouped-neighbor traversal per center using
  checked degree/leaf/overlap totals. Preserve outer-node inequality, self-loops,
  physical parallel/reciprocal multiplicities and final scalar overflow checks;
  no additional scratch allocation or change to wedge anti-joins.
- Prepay non-anti wedge physical-slot scan work in bounded 256-slot chunks to
  amortize budget access. Successful work totals stay exact, group callbacks
  retain separate charges, and final deadline checks include empty rows. Tight
  budgets can conservatively reject a partly affordable chunk before scanning.
- Narrow non-anti wedge multiplicity/degree to checked `u32` and weighted leaf
  totals to checked `u64`, using the typed index's global physical-edge bound.
  Derive multiplicities from drained adjacency spans while keeping scan indices
  wide. Overlap, final products/subtraction and total count remain `u128`;
  shared leaf storage, anti-joins and work/allocation budgets are unchanged.
- Account for label comparison/lookup bytes in scalar and forest counts, and
  property-map searches in null probes. Constant-time label cardinality shortcuts
  remain; tight budgets may now reject previously undercharged queries.
- Correct reference relationship uniqueness within one `MATCH`, including comma
  paths, physical parallel edges, optional padding and mixed fixed/variable paths.
  Named fixed relationships keep physical identity through `WITH` aliases,
  bare-variable grouping and `WITH DISTINCT`;
  repeated relationship-list bindings now fail explicitly instead of overwriting.
- Connect indexed Memory counts and opt-in Turso/PostgreSQL scalar SQL counts
  to LSQB observations. Bind optimized-plan admission to query hashes and exact
  SQL digests; exempt only proven non-materializing counts from the Rust
  match-row ceiling. All 22 example cases pass offline against the pinned
  oracle on Memory and embedded Turso; all 22 pinned Memory queries now select
  non-materializing plans. Native, non-publication SF0.1/SF0.3 diagnostics also
  match all 22 pinned counts; qualified container comparisons and live PostgreSQL
  validation remain pending. Sail has
  not opted into scalar SQL counts.
- Restrict scalar SQL filter admission to conjunctions of genuine property/string
  equality with exact JSON payload-type and byte-comparison checks. Numeric,
  inline-label and other unproven predicates retain older routes; dialects opt
  into exact rendering through a default-unsupported hook.
- Decline SQL segment/multi-pattern joins with overlapping relationship types:
  nullable or duplicate edge IDs cannot establish physical relationship
  uniqueness. Preserve the oracle queries through the corrected reference
  fallback rather than accepting duplicate relationship use in SQL joins.
- Push Surreal HTTP and SDK edge endpoint predicates to the server using full
  logical record keys, preserving table independence and client-side filtering.
  Live query-plan and performance validation remain pending.
- Add a bounded, load-once Memory profiling diagnostic with pinned dataset/plan
  checks, per-iteration count oracles and flushed progress. Its distinct schema
  explicitly excludes publication; it does not modify benchmark observations
  or the comparison lifecycle.

- Gate native qualification startup on a retained, fail-closed host CPU screen.
  Preserve the completed 264-pass SF0.3 diagnostic as performance-excluded;
  publish the timing correction without changing frozen correctness evidence.

- Stop the three confirmed orphaned test loops after user authorization. Replace
  unbounded timeout-test spinners with five-second self-expiring fixtures and
  bound escaped-worker readiness polling; the original leak cause remains open.

- Record orphaned CPU-spinning benchmark test workers and quarantine the
  overlapping native SF0.3 run from performance export pending cleanup and rerun.

- Add a read-only native-run progress summary with load percentages, observed
  outcomes, warm-up/measurement counts and current query. Partial journal lines
  remain explicit; a snapshot never implies process liveness or publication.

- Require the native Neo4j runner's network to be internal and the server to
  attach exclusively to that exact network; retain the inspected network identity.
  Include that record in frozen exports and require it for SF0.3 publication;
  flush evidence payloads to disk before writing the completed bundle manifest.

- Publish independently verified Helix Rust SDK example evidence at
  adversari.al/graph: 108 baseline and 156 adversarial observations, with
  load/query/setup/recovery timings and both client/server build provenance.
  Retain the separate direct HTTP lane and materialize-reference classification.

- Freeze Helix SDK example evidence with pinned client and source-built server
  recipes, logs and provenance; reject altered server identities or build bytes
  before export. Independent site admission remains pending.

- Run Helix SDK3 against the source-built `/v2/query` server: 108 baseline and
  156 adversarial example observations pass. Add pinned runtime/count/timing
  audit and mutation tests; independent site publication remains pending.

- Correct duplicate book chapter numbers by letting the renderer number the
  thirteen chapters, with unnumbered preface and conclusion.

- Bound cleanup of the book diagram renderer's owned browser after a successful
  render. Validate a fresh PNG before atomically replacing a diagram, and retain
  explicit render/cleanup progress rather than waiting indefinitely on shutdown.

- Add recorded, private-network Helix SDK startup probes with a bounded
  readiness window, restart detection and isolated probe-container cleanup.

- Document the separate source-built Helix SDK3 server candidate, pinned Docker
  recipe and private-network qualification requirements; preserve the HTTP/v1
  service and disclose that live SDK3 qualification is still pending.

- Publish the independently verified Surreal Rust SDK example comparison at
  adversari.al/graph: 108 baseline and 156 adversarial observations, separate
  load/setup/query/recovery timings, and preserved HTTP lane identity.

- Freeze audited SDK observations and client build provenance in hashed evidence
  bundles, without treating diagnostic verification as publication admission.

- Accept content-addressed, source-pinned local SDK server images for Docker
  qualification, with image-level revision and platform checks. Registry
  services retain their digest pinning; publication admission remains separate.

- Migrate the private Helix Rust SDK adapter to `helix-db` 3.0.0 and its typed
  nested-AST query requests. Preserve the separate direct HTTP/v1 adapter and
  its existing predicate semantics. Unit tests pass; SDK/v2 service runtime
  qualification remains pending and is not inferred from HTTP evidence.

- Retain long-running build/test output with durable periodic progress and
  terminal exit records, without imposing a guessed job completion timeout.

- Add distinct `helix-sdk` and `surreal-sdk` matrix executable lanes without
  replacing the HTTP lanes. Record SDK transports, separate Surreal datasets,
  and retain materialization and fail-closed recovery semantics. Docker
  qualification and independent publication admission remain pending.

- Gate native Neo4j benchmark startup on a successful Bolt scalar query, not
  merely a running Docker container. Bound readiness to 120 seconds, report
  each attempt, and stop the selected disposable server on startup failure;
  readiness is outside the query measurement boundary.

- Publish the Sail Docker reproduction guide with pinned public base/wheel inputs,
  explicit Grust-built provenance, and source-built comparison admission requirements.
  Add retained source-build evidence and a fresh-process shared-session qualification
  probe. The probe verifies borrower reads, owner-only release, and server health;
  enable coordinator-owned, once-loaded Sail sessions in the benchmark runner,
  with fresh borrowing workers and bounded owner-only cleanup. All 22 example
  queries pass a host-client/Docker-service diagnostic; fully Dockerized repeated
  performance evidence and publication admission remain separate requirements.
  The source-built private-network Docker example run now passes all 264 W2/R10
  observations, with retained runtime snapshots and an independent diagnostic
  count/journal/timing audit. Public evidence admission remains pending.
  Freeze source-built Sail handoff bundles with build provenance and structured
  observations; reject arbitrary skipped queries or relabeled execution plans.

- Derive receipt-bound performance summaries with measured query/setup/recovery
  distributions, per-sample boundary totals, and separate coordinator loading.
  Retain raw samples and failures; suppress timing summaries after failed
  warm-ups or measurements and do not label reciprocal latency as throughput.

- Begin a native Neo4j comparison lane using the pinned Neo4j Labs Rust driver,
  with Docker example, SF0.1 and SF0.3 qualification (nine baseline queries and thirteen attacks),
  incremental observations, isolated query processes, coordinator deadlines,
  independently checked server recovery, and an oracle/journal diagnostic audit.
  Retain Docker runtime metadata before watchdog cleanup and distinguish a
  transaction disappearing after worker exit from acknowledged termination.
  Race-fix Docker deadline/recovery probes pass; publication receipts remain pending;
  diagnostics are not published rankings.

- Native Neo4j benchmark sampling now distinguishes warm-ups from measured
  repetitions, with per-sample process isolation, recovery, and durable progress.
  The independent audit rejects missing, reordered, or mislabeled samples and
  reports warm-up failures separately from measured outcomes.
  Align subsequent native runs with Grust's phase-major rotating query schedule;
  preserve earlier query-major runs as a separate diagnostic cohort.
  Require runtime evidence plus rotating W2/R10/60-second sampling through an
  explicit comparison-cohort audit gate; the example cohort passes all 264 samples.
  Qualify the SF0.3 rotating client profile so its runtime audit can run; the
  scale-0.3 cohort passes all 264 samples on the linux/amd64 server image.
  Retain a failed cell container's own exit and OOM flag in the watchdog's
  completion record, and declare a cell whose container exceeded its memory
  limit from that evidence instead of stopping the matrix at a missing
  component report.
  Carry such a declaration through the merged matrix, the evidence validator
  and the publication receipt: the matrix is accounted for rather than
  complete, and the receipt names every cell that did not run.
  Name that outcome `cell.memory-exceeded`: the container the kernel takes away
  holds the harness runner, and a configured service runs under its own
  separate limit, so the declaration is about the harness's envelope for a plan
  and not about the backend's memory demand. `measure-cell-budget.sh` measures
  what such a cell needs to finish.

- LanceDB adapter: load a whole graph through a bulk path with its own
  `bulk_batch_size` (50,000 rows by default), open each table once for the
  load instead of once per batch, and compact every table the load touched.
  The incremental `batch_size` is unchanged.
  Export frozen, checksummed native evidence bundles for independent site admission,
  without treating the transport manifest as a publication receipt.

- Benchmark-only: use 10,000-row Sail bulk-write batches and expose aggregate
  completed-chunk/node/edge counters during projected coordinator loading.
  Worker setup remains private and query observations remain separately recorded.

## 0.13.2 "Krill" - 2026-09-05

Krill is a scoped patch for `grust-cypher`, `grust-sail`, and `grust-graph`.
`grust-surreal` remains 0.13.1; other publishable crates remain 0.13.0.

- Added consuming `SailGraphStore::close()` to release caller-owned remote
  sessions explicitly. Benchmark workers close Sail sessions after emitting
  their results, within the bounded recovery phase, and the coordinator closes
  its preliminary session before starting workers.
- Fixed Sail portable count projections failing on Arrow integer row-presence
  markers (`SELECT 1`), discovered by executing LSQB q1 on Sail 0.7.1.
  Decoding preserves match multiplicity, column order, and null values.
- Corrected Sail's recursive-CTE capability declaration after a live zero-hop
  attack exposed an unresolved recursive relation. Variable-length path reads
  use the shared reference fallback rather than submitting unsupported SQL.
- Record each completed LSQB observation immediately as a flushed JSON line in
  the host-captured cell log, including counts, timing, termination, and recovery.
  Interrupted runs retain diagnostics without claiming a completion receipt.
- Upgraded LSQB comparison evidence to schema v3 with a fresh process-group
  worker per observation, nonce-bound READY/GO timing, hard query deadlines,
  bounded TERM/KILL/reap handling, backend-specific recovery proofs, and
  secret-safe start/ready/finish progress records.
- Removed the downloaded-scale Memory benchmark's duplicate full-graph clone:
  lazy projected-FK chunks now build the sole owned in-process reference graph,
  and their decode time remains disclosed in `load_ns`.
- Made the upstream benchmark launcher work under macOS Bash 3.2 at the
  example scale, preserve a failing exit status across cleanup, use portable
  BSD/GNU `chmod` argument ordering for authenticated dataset snapshots, and
  accept the stock macOS Python 3.9 interpreter for external-service
  qualification.
- Added concrete opt-in qualification records for PostgreSQL 19 Beta 3 SQL/PGQ
  and the isolated Helix local runtime, while retaining fail-closed defaults
  and documenting why Sail still needs a registry-published immutable image.
- Made external-service image attestation portable across Docker image stores:
  the declared identity remains a platform-manifest reference plus its registry
  config digest, while receipts separately bind the manifest digest and the
  locally observed runtime ID. Legacy config-ID and containerd manifest-ID
  representations are accepted only when the container and local image agree.
- Kept the receipt issuer's isolated semantic-validation sandbox complete when
  merge hardening introduced the shared output-safety helper, with a real
  end-to-end fixture that prevents missing validator dependencies from recurring.

## 0.13.1 "Crayfish" - 2026-09-04

Crayfish is a scoped registry patch for `grust-sail`, `grust-surreal`, and the
`grust-graph` facade. All other publishable crates remain on 0.13.0.

### Credential safety

- Stop rendering the configured Sail Spark Connect endpoint or its transport
  error in connection failures. Endpoints can carry credentials or signed
  query parameters, so failures now use a stable secret-free message.

### SurrealDB correctness

- Preserve the original case-sensitive Grust label in SurrealDB rows instead
  of reconstructing it from the normalized physical table name, while keeping
  a backward-compatible physical-label fallback for existing data.
- Decode record IDs by separating the table at the first colon, so logical IDs
  such as `City:4` no longer return as a truncated `4\`` value. Reserve both
  internal label fields against user schema and property collisions.

### Benchmarks and evidence

- Expanded the LSQB-derived Docker harness from a three-backend compatibility
  harness to a rectangular, machine-validated twelve-backend matrix. Reports
  preserve pass, mismatch, timeout, unsupported, unavailable, error, and
  not-applicable outcomes; disclose native, row-source, materialization, and
  in-process execution classes; and bind source, adapter, dataset, image,
  resource, query, warm-up, and measurement provenance instead of blending
  unlike timings.
- Extended the adversari.al graph suite to 13 deterministic count-oracle cases
  and 14 bounded-policy attacks, including zero-hop paths, Unicode and null
  semantics, parser trivia, edge scans, query-byte and path-hop pressure,
  invalid Unicode, graph selection, and unterminated comments.
- Added authenticated LSQB SF0.1/SF0.3 acquisition, an independently validated
  unchanged-upstream Ladybug runner, strict evidence merge/summarization
  checks, and a larger GDC workload ladder covering SNB BI, SNB Interactive,
  FinBench, Graphalytics, and Text2GraphQuery. Derived runs retain the required
  “These are not LDBC Benchmark Results” boundary.
- Made larger-scale evidence fail closed: streamed loaders avoid duplicate
  source graphs; plan-specific logical-row bounds refuse unsafe Rust
  materialization; late non-yielding work becomes a timeout; compiled features,
  qualified service failures, output overwrite/symlink hazards, and unlike
  per-component resource envelopes cannot masquerade as comparable passes.
  Publication receipts bind normalized watchdog completion attestations for
  all 24 backend-suite cells and the policy cell; the separate upstream
  Ladybug receipt binds its own record. Each attestation fixes the configured
  hard limit, elapsed wall time, child exit status, and exact container ID,
  name, project, and service observed by the narrowly scoped supervisor.

## 0.13.0 "Prawn" - 2026-09-04

Prawn returns every publishable Grust crate to one lockstep release line. It
includes the complete surface that was only partially shipped in the scoped
0.12.1 Shrimp registry patch, plus the later safety, semantic-model,
performance, backend, documentation, and benchmark work recorded below.

### Release and portability

- Moved all 15 publishable Grust crates and their intra-workspace dependency
  requirements to 0.13.0; keep HelixDB, LadybugDB, QueryGraph Memory, and
  examples explicitly unpublished while testing them in the workspace.
- Removed the repository-wide absolute Apple SDK include path that mixed Xcode
  and Command Line Tools headers. Native C++ troubleshooting now derives any
  required fallback from the active `xcrun` SDK in the invoking shell.
- Reconciled the Shrimp patch history, current release marker, README and book
  examples, completed goal records, GQL claim scope, and centralized FirstPair
  book/TextPack handoff for the named Prawn release.
- Included Apache Ossie's `NOTICE` and Apache-2.0 text beside the exact upstream
  TPC-DS fixture in the published facade archive. The release gate
  `scripts/verify-package-attribution.sh` inspects the actual `.crate` archive
  so a future package cannot silently drop the fixture or its attribution.
- Qualified the backend dependency line rather than mechanically selecting the
  highest version: Redis advances to 1.6.0 with FalkorDB v4.20.4, SurrealDB and
  its Docker service advance to 3.2.4 with reqwest 0.13.4, pgGraph's live image
  advances to 1.2.0, tokio-postgres advances to 0.7.18, and Turso advances from
  a prerelease to stable 0.7.2. The applicable focused and live integration
  gates pass.
- Deliberately held LanceDB at 0.30.0 after the 0.38.0 default-feature,
  local-mode build failed inside upstream `lancedb`: `job.rs` references the
  remote-only `Error::Http` variant when `remote` is disabled. Held the
  unpublished Helix adapter at exact `helix-db` 2.0.0 after the 3.0.0 probe
  removed `DynamicQueryRequest`/`dynamic_query`, changed `Client::query`, and
  targeted `/v2/query` while the checked Helix v3.0.1 server still exposed
  `/v1/query`.

### Safety and semantic projection

- Added a backend-neutral semantic graph taxonomy for versioned models,
  datasets, fields, relationships, and metrics. Projection now validates
  SHA-256 identities, names, references, and uniqueness, uses collision-safe
  identity components, and preserves separately named parallel relationships
  in the constructed `Graph` with explicit edge IDs. Persisted multi-edge
  preservation remains a backend capability; structurally keyed stores can
  collapse same-endpoint, same-label edges.
- Replaced the synthetic Ossie proof with the exact Apache Ossie TPC-DS YAML
  from upstream commit `ddb19f1b135a61c65603f4823a3526e2fab00cf1`. The
  packaged fixture must match SHA-256
  `bafbdc9d0e304ab22a40592f2b6bdfd45cc399c566533cd71343d33380c0d6e1`
  before parsing and replay-stably projecting five datasets, 31 fields, five
  metrics, and four relationships.

- Added a parser-backed bounded read policy for applications that expose a
  deliberately small in-memory GQL/Cypher surface. It rejects updating clauses,
  graph selection, procedures, unbounded paths, and non-literal limits from the
  typed AST, then enforces parameter/graph/output byte ceilings, graph counts,
  cumulative candidate work, intermediate bytes, and path hops, result rows,
  per-range allocation, and a cooperative wall-clock timeout. The cumulative
  byte budget includes cloned bindings, expression and aggregate results, and
  DISTINCT/GROUP serialization, preventing pre-`LIMIT` projection amplification.
  All reference reads retain a global
  hard ceiling on scalar and table-valued `range()` allocation. Correlated
  `CALL { ... }` index construction and catalog-procedure graph scans are now
  charged on every invocation, closing a per-outer-row rescan bypass against
  both the candidate-work limit and cooperative deadline. Authorization, remote
  deadlines, and process isolation remain host responsibilities.

- Made non-returning PostgreSQL and Turso
  `execute_cypher_mutation_plan` calls atomic on their transactional stores.
  Each executor rejects unsupported lowering before writing, then preserves
  source order inside one isolated transaction. Their shared connections are
  serialized for the complete transaction, and the next caller rolls back an
  abandoned transaction if cancellation drops a future during `BEGIN`, a
  statement, or `COMMIT`. The generic
  write-with-`RETURN` helper remains sequential because later operations may
  consume intermediate bindings; it is not a whole-statement atomicity
  boundary. Explicit transaction scripts continue to batch supported
  mutations.
- Made PostgreSQL's public raw `execute` surface explicitly autocommit-only.
  Its lexical guard rejects transaction-control statements in multi-statement
  SQL while ignoring lookalike words in strings, quoted identifiers,
  dollar-quoted bodies, and comments; PostgreSQL PGQ inherits the same guard.
  Transaction helpers set their recovery marker before `BEGIN`, and every
  serialized connection user first rolls back an in-flight transaction left
  uncertain by cancellation.

### Backend correctness and graph performance

- Hardened the dynamic graph backends before query construction or transport.
  FalkorDB validates configurable identity-property names, schema and
  complete-graph label/relationship claims after lossy normalization, and
  losslessly quoted property names, prevents a property map from overwriting
  the configured structural ID, and no longer includes Redis URLs or
  credentials in pool/query errors. Helix rejects unsafe
  schema names, normalized relationship collisions, and attempts to overwrite
  node/edge structural metadata, preflights complete graph batches, and omits
  configured URLs from transport errors. SurrealDB uses lossless SurrealQL
  identifier quoting, rejects ambiguous normalized record-table mappings and
  reserved structural-field writes, validates schema/configuration and every
  batch before I/O, preserves optional edge IDs in `edge_id`, and redacts URLs
  from HTTP/WebSocket failures.
- Added shared physical-schema claim validation for backends whose logical
  names are lowered into native object namespaces. FalkorDB, Helix, LadybugDB,
  LanceDB, and Sail now reject both lossy-name collisions and exact duplicate
  declarations before emitting schema or write operations.
- Added `validate_edge_key_components` and `checked_edge_key` for every
  persistence/export path that materializes Grust's compatibility edge key.
  CocoIndex, Cypher capture/refetch, LadybugDB, LanceDB, and Sail now reject
  U+001F in source IDs, labels, target IDs, or explicit edge IDs before two
  distinct edges can alias. Mixed explicit/idless equality additionally checks
  the structural owner. LadybugDB also rejects U+001F in node IDs before its
  managed metadata index can confuse a user record with a table marker.
  Separately, `GraphValue` relationship deduplication now
  uses length-framed identity components, so its payloads require no reserved
  delimiter and crafted explicit/structural identities remain distinct.
- Made recursive SQL walk pushdown safe for arbitrary `NodeId` text. PostgreSQL,
  Spark SQL, and the generic SQLite dialect hex-encode IDs into delimiter-free
  visited-set tokens before framing them; a dialect without both recursive-CTE
  support and such an encoder declines variable-length and shortest-walk
  pushdown instead of relying on a delimiter that may occur in an ID.

- Added a Docker-reproducible LSQB compatibility and adversarial-query
  harness under `benchmarks/lsqb`. The unchanged upstream baseline pins Graph
  Data Council LSQB commit `242cb2fd31340ca688954cb94794d74c0d5b6f92`,
  LadybugDB 0.19.0, and a digest-pinned Python 3.12.11 container; five
  repetitions over `sfexample` match all nine expected result counts in 45/45
  executions. A separately labeled Grust adapter is configured to run the same
  28-node/72-edge fixture plus eight adversari.al count attacks across Memory,
  Turso, and PostgreSQL 18.6 with a clean load per repetition. Nine additional,
  backend-neutral attacks require stable policy rejections for unbounded paths,
  range allocation,
  candidate work, updating-clause smuggling, forbidden procedures, and excess
  UNION arms, plus cumulative intermediate projection, correlated subquery
  replanning, and correlated catalog rescans. Those eight count attacks plus
  nine policy attacks are 17 separate
  adversari.al attacks; each storage-backend cell has 17 count oracles (nine
  LSQB-derived plus eight adversarial), while policy is one backend-neutral
  rejection track. This is a reproducibility and compatibility microbenchmark,
  not a performance ranking: LSQB is GDC-maintained but not an official LDBC
  benchmark. Tracked evidence now covers the unchanged upstream 45/45 run and
  clean Grust revision `2680c451`: 135/135 LSQB-derived compatibility
  observations, 120/120 adversarial count observations, and 9/9 bounded-policy
  rejections passed.
  These are not LDBC Benchmark Results.
- Removed the Rust 1.96 strict-Clippy debt from the Cypher and Sail execution
  paths without adding lint suppressions. Writable `RETURN` parsing and
  evaluation now use named scope, aggregate, and cache contexts; Sail mutation
  execution uses typed capture/output objects and operation views instead of
  parallel optional tuples and long argument lists. Shared schema SQL now takes
  an explicit table layout, and the remaining first-party workspace findings
  in PostgreSQL control flow and test/benchmark code are resolved.
- Fixed typed Sail schemas that explicitly declare the node `id` property.
  The property now reuses the one structural identity column throughout table
  descriptors, Delta DDL, and staged merges; incompatible non-string identity
  declarations fail before SQL reaches Sail.
- Added the defaulted `GraphSqlDialect::max_identifier_bytes` hook. PostgreSQL
  reports its 63-byte ceiling, so typed node/edge views and property indexes at
  that limit remain valid while longer generated names fail with
  `GrustError::Schema` before PostgreSQL can silently truncate or collide them.
  Dialects without a declared limit retain their previous behavior.
- Updated the internal, unpublished LadybugDB adapter from `lbug` 0.17.1 to
  0.20.2 while retaining its Arrow 55 IPC boundary. The unchanged upstream
  LSQB reference run deliberately keeps Ladybug 0.19.0 because that is the
  version selected by the pinned upstream scripts.
- Verified the QueryGraph stack against the exact optimized graph-enabled Sail
  `c5309365` artifact: 26 adapter tests, the dedicated non-null and temp-view
  gates, and both governed cognition parity/secrecy tests pass. The same
  artifact also accepts Typesec's 5-node, 4-edge typed company schema that
  exposed the duplicate-identity-column defect.
- Added statistically sampled Criterion coverage for graph index construction,
  edge-key materialization, unique-property validation, and in-memory graph
  point writes, filtered reads, traversal, and bulk upserts at realistic graph
  sizes. Coverage now also isolates constrained edge writes, deep and
  high-fanout traversal, and adjacency-sensitive node and edge deletion.
- Replaced quadratic graph property-uniqueness scans with hash-bucketed,
  collision-checked value tracking that preserves floating-point and JSON
  equality semantics.
- Removed full-graph cloning and validation staging from schemaless in-memory
  point writes and bulk upserts; constrained stores retain the same pre-write
  validation path.
- Added maintained incoming and outgoing adjacency indexes to the in-memory
  backend. Endpoint-filtered reads and traversals now inspect only incident
  edges, while all mutation paths update the indexes through shared helpers.
- In-memory node, endpoint-edge, and Cypher relationship deletion now resolve
  incident keys through those adjacency indexes instead of scanning the full
  edge map. At 10,000 edges, deleting a node with two incident edges improves
  from about 42.1 microseconds to 100 nanoseconds, and deleting one matched
  edge from 52.1 microseconds to 63 nanoseconds.
- Replaced constrained point-write graph snapshots with focused node, edge,
  uniqueness, native-constraint, and incident-endpoint validation. Bulk writes
  still validate one complete staged graph so cross-item constraints remain
  atomic and fail before mutation.

### Integration reliability

- Bounded each Sail integration command with a configurable timeout. A stalled
  live phase now fails the harness instead of leaving the release gate running
  indefinitely.

- Replaced `querygraph-memory`'s TypeSec sibling paths with the exact reviewed
  public Git revision, so the governed cognition crate can build and test from
  a clean Grust checkout.

- Recorded a passing focused live Sail integration gate for the governed
  cognition substrate: 26 Sail adapter tests, two live backend checks, and two
  cognition reference-parity and evidence-secrecy cases. The documentation
  keeps this explicitly local-source verification separate from Marciana's
  remote-reachable Sail compatibility baseline.

### Governed memory, FirstPair, and query execution

- Changed `querygraph-memory` relationship facts from one structurally
  deduplicated direct edge to a hash-stable, per-record `MemoryRelation`
  assertion node between the two entities. Distinct records can now retain
  independent lineage for the same endpoints and relationship name. Assertion
  IDs hash fixed-width length-prefixed components and remain identical across
  32- and 64-bit hosts. Neighborhood reads can cross any mixture of legacy
  direct `RELATES` edges and current assertion-node relationships at
  successive logical hops, while tombstone preflight discovers the record's
  assertion nodes and legacy fact edges before deleting that discovered set
  with the record as one atomic batch on transactional stores. Discovery is
  outside that transaction, so callers must synchronize concurrent link and
  tombstone operations.

- Updated `grust-sail` for current Sail Spark Connect sessions. Each session
  can leave its warehouse server-managed or configure and verify an explicit
  absolute override. Client-local session-scoped warehouses are opt-in and
  caller-cleaned, keeping the default safe for remote endpoints and persistent
  server catalogs. Generated Delta tables retain named columns and structural
  non-null constraints, registry values are staged through Arrow, and session
  temp views can be dropped safely and idempotently.

- Added bounded Arrow IPC collection to `grust-sail`. Accepted batches move
  into the collection without a second copy; inclusive chunk and cumulative
  byte limits fail before retention. Spark Connect accepts at most a 17 MiB
  decoded message, reserving 16 MiB for Arrow payload and 1 MiB for protobuf
  envelope metadata.

- Added canonical cognition operation parsing and hardened planning around one
  TypeSec-authorized input and binding. LakeCat evidence, projection, field
  mapping, source revisions, and label joins are checked before Sail runs;
  proposals are born bound. Live Sail uses collision-safe temp views and always
  attempts cleanup under its own bounded deadline, including after caller
  cancellation; operation and abort time are bounded independently. It
  requires the complete exact result set under
  fixed source-count, authorized-input byte, Arrow, result, projection,
  identity, mutation, and local-work budgets shared with TypeSec and the
  reference engine. Cognition rejects excessive encoded Arrow collection and
  declared row, buffer, or decompressed sizes before `StreamReader` allocates
  result arrays, then rechecks the complete result locally. Native provenance
  is accepted only for exact bounded operation identities. Deduplicate and
  reconcile each use an explicit version-2 semantic contract shared by their
  reference and Sail profiles; package/build versions are implementation
  metadata and never mutation authority. Legacy version-1 or package-bound
  intents fail closed and require fresh authorization. Fixed host-selectable
  profiles let a trusted composition registry bind an engine independently and
  check signed intent before authorized input is loaded; public engine
  implementations cannot self-report identity, and Sail executors cannot
  choose a version after execution. TypeSec canonical proposal validation also
  rejects an executor's malformed or over-budget output before it leaves the
  engine wrapper. The adapter exposes only fixed failure categories rather than
  caller, source, or adapter text.
  Reference and Sail proposals now share permutation-stable canonical dedup and
  reconciliation planning, including ID tie-breaking at Sail's staged timestamp
  precision. Optional TypeSec-governed source scopes are preserved through
  bound proposals, durable audit evidence, retry, and reopen; explicit local
  cognition remains scope-free. Bound proposal schema version 4 now binds the
  immutable snapshot digest separately from the LakeCat grant digest and names
  an explicit `mutated` or `no_change` effect. Reference and Sail engines derive
  that effect from the complete canonical plan. Durable outcome schema version
  3 validates TypeSec audit schema version 2, including the same effect,
  separate snapshot identity, and authority-revalidation time. Audit and
  commit-envelope digest domains are version 3, so this evidence epoch cannot
  collide with either earlier layout.

- Added durable cognition jobs and atomic application to `querygraph-memory`.
  Renewable bounded leases, cancellation, retry, digest-only proposal state,
  subject-and-purpose-scoped job identities, and an ID-only leased outbox
  survive reopen. Every derived job, outcome, audit, outbox, and ledger address
  includes TypeSec's opaque authority-scope digest. Only TypeSec's opaque
  prepared token can atomically exact-guard sources, apply the exact memory
  operations and ID-only outbox, write audit evidence, persist the outcome, and
  complete the job. A typed no-change decision has no memory or outbox
  mutations, retains the prior memory version, and still commits its job,
  audit, outcome, and guarded ledger atomically.
  Scheduler submission, proposal staging, commit, and recovery bind the same
  verified TypeDID request digest.
  Idempotent recovery cross-validates the durable job, authority scope, audit,
  outcome, and backend receipt; raw bearer, owner, failure, proposal, and
  plaintext values are never persisted in scheduler metadata. A job's logical
  transition time is caller-supplied; completed jobs bind it explicitly to
  TypeSec preparation, and their completion digest is the exact canonical
  TypeSec prepared digest for either effect, never the resulting memory
  version. Authoritative backend commit time exists only in the outcome and
  receipt. Backend commit time must
  be canonical RFC 3339 and
  must not predate preparation; malformed or regressive evidence fails closed
  instead of being relabeled as another phase. Commit-then-response-loss tests
  prove that retry and reopen retain exactly one mutation, job, audit, outcome,
  and outbox manifest. Concurrent identical applications recover the original
  byte-stable evidence even when completion wins between the initial recovery
  lookup and either the exact-source or staged-job read.
  Recovery checks durable schema versions before deserialization, rejects
  checked-in legacy outcome and audit shapes precisely, and requires affected
  memory IDs to retain TypeSec's strict canonical order.
  Scheduler and outbox methods are explicitly storage primitives for an
  authenticated trusted worker pool: submitters and transferable workers may
  differ, scoped keys and owner strings are not credentials, and active lease
  or claim tokens are bearer credentials for worker transitions.

- Clarified that these Grust capabilities are the generic governed-cognition
  substrate; standalone Marciana still owns authenticated orchestration,
  product receipts, and the pending qg-rust cognition cutover.

- Added a domain-neutral guarded graph commit capability and a durable Turso
  implementation. Exact-node and absence expectations, graph mutations, and a
  backend-issued commit identity now share one transaction; identical retries
  return the original receipt, while idempotency-key digest collisions fail
  closed. A read-only guarded-receipt lookup recovers an exact prior commit
  without issuing a probe mutation. Turso mints its receipt time at nanosecond
  precision immediately before the ledger insert, persists and replays those
  exact backend-issued transaction-boundary bytes, and rejects a malformed
  durable timestamp without disclosing it.

- Added ignored live-Sail conformance tests for Marciana cognition that
  separately compare distributed deduplication and reconciliation with the
  reference engine, prove repeated jobs are deterministic, and reject governed
  inputs or source plaintext in audit evidence. The integration launcher now
  runs them alongside `grust-sail`, accepts an explicit `SAIL_TEST_BIN`, and no
  longer silently substitutes an unrelated `sail` executable from `PATH` for the
  configured source checkout.

- Added an optional live Spark Connect cognition executor to the private
  `querygraph-memory` integration crate. Governed memories are staged in a
  session-local Arrow view under a random collision-safe name. Sail computes
  bounded deduplication and reconciliation candidates, and only inert TypeSec
  plans return; authorization secrets are never staged or logged.
- Made the cognition engine and Sail executor contracts asynchronous so live
  Spark Connect execution does not block a runtime worker.

- **QueryGraph-native Marciana cognition boundary:** `querygraph-memory` now
  binds cognition jobs to a hash-verified LakeCat/Iceberg snapshot, governed
  Sail scan projection, verified TypeDID subject, purpose, and authorization
  receipt. Reference analytics and injectable Sail executors emit inert
  TypeSec cognition proposals without receiving a store handle.

- **Grust book covers durable TypeSec Memory:** expanded the architecture tour
  with the implemented `querygraph-memory` boundary, including opaque record
  storage, the `MemoryRecord`/`MemoryEntity` graph, space-only pushdown,
  transactional Turso consolidation, the sanctioned synchronous/asynchronous
  bridge, privacy-aware reference vector ranking, inert cognition plans, and
  the explicit post-v1 security, scale, and hosting limits.

- **First Pair Press image cover:** adapted the live Grust announcement
  headboard into a portrait cover, set Alexy Khrabrov as the sole author,
  added the reusable First Pair Press publisher seal, and wired the same image
  into PDF, EPUB, MOBI, and hosted HTML output.

- **Unified FirstPair book build:** `book.build.json` now delegates the Grust
  book to FirstPair's pinned Pandoc/Typst and Mermaid toolchain while retaining
  `build.mjs`, EPUB repair, and page-label hooks. PDF, EPUB, MOBI, single-file
  HTML, chapter HTML, manifest links, and rendered layout checks share one
  publish-complete contract.

- **PostgreSQL joins the executing Cypher conformance set**
  (`docs/GQL_POSTGRES_EXECUTOR_GOAL.md`, complete): `PostgresGraphStore` now
  implements `CypherMutationExecutor` (resolved writes, bounded matched-node
  patches via `jsonb` predicates, atomic `CypherTransaction` batches through
  its transactional `apply_mutations`) and `run_read_query` pushdown over the
  universal tables via a new `PostgresReadDialect` — tagged-jsonb extraction
  (`#>> ARRAY['key','value']`), `position()`/`right()` string predicates,
  `generate_series` for `tvf.range`, `jsonb_object_keys` for
  `db.propertyKeys`, byte-order (`COLLATE "C"`) procedure sorts, and
  `WITH RECURSIVE` variable-length paths (the first non-SQLite engine to push
  them). Shortest paths and correlated `tvf.keys` are honestly gated off (no
  insertion-ordered rowid; jsonb key order) and fall back to the reference;
  `ORDER BY` stays in the reference (collation). Proven by a gated live
  differential suite (`GRUST_PG_URL`) run green against PostgreSQL 17:
  pushed reads, fallback reads, writes, and transaction scripts all match the
  Memory reference. The pushdown walk CTEs' remaining SQLite-isms (`instr`,
  edge columns in the recursive step, `ORDER BY` collation under `DISTINCT`)
  became dialect hooks; the executing set is now Memory/Sail/Turso/Postgres.

- **`querygraph-memory` durable v1:** typesec-memory's `MemoryStore` runs over
  compatible Grust `GraphMutationStore` backends, with Turso/libSQL as the
  default and proven persistent path. `TursoMemoryStore::open(path)` creates
  and bootstraps the database on the store-owned bridge runtime; the advanced
  `open_with_config` constructor supports table-prefix and journal tuning.
  The bridge now owns Tokio I/O/time drivers and shuts down safely when the
  store is dropped inside an async service. File-backed integration tests run
  the full TypeSec conformance corpus, close/reopen the database, preserve a
  capability-gated transactional consolidation and its SecLib label join,
  and exercise construction and use from inside an existing Tokio runtime.
  Records and their entity graph remain incremental nodes/edges, space scope
  is pushed into the backend, and all remaining query dimensions use the
  shared conformance-pinned matcher. The reference `VectorIndex` enforces
  embedding privacy, analytics emit plans through the vault front door, and
  the shared-store test proves vault-level tenant authorization. TypeSec
  Memory is published in `0.13.0` Lido; this adapter remains
  `publish = false` pending a deliberate Grust release/distribution decision;
  its TypeSec contract is pinned to the reviewed public Git revision so clean
  checkout and integration CI builds do not require a sibling repository. LanceDB ANN,
  Sail-distributed cognition, fuller GQL pushdown, and a hosted multi-tenant
  service are explicitly post-v1 work rather than claims of this release. The
  adapter is consumed by qg-rust's signed-only memory API and its qg-python
  Pydantic AI v2 restart demonstration. The workspace lock is aligned with
  TypeSec `0.13.0` Lido.

- **Turso joins the read-pushdown consumers**: `TursoGraphStore::run_read_query`
  now pushes the portable read subset into SQL over the universal tables via a
  new `TursoReadDialect` — tagged-JSON property extraction (`$.key.value`),
  `from_id`/`to_id`/`label` edge columns (the pushdown SQL builders'
  edge-column names are now dialect-owned), typed-JSON ordering — with the
  embedded engine's gaps honestly gated (`WITH RECURSIVE` and `json_each`
  leaves report unsupported and fall back to the reference over
  `read_graph()`). The Turso backend descriptor flips `portable_reads` and
  `read_pushdown` to true. A store-level differential test runs pushed and
  gated shapes end-to-end against the reference.

- **Reference executor expression gaps closed**: map literals evaluate,
  list/map indexing works (negative indices, out-of-range → NULL),
  `RETURN DISTINCT … ORDER BY` sorts deduplicated rows by projected items,
  `RETURN *`/`WITH *` combine with aggregates (star variables become grouping
  keys), and multi-label patterns are conjunctive over the single-label model
  instead of erroring.

- **PUSHDOWN2 PM3**: correlated subqueries and shortest paths now push into
  backend SQL. A correlated inner `WHERE` (e.g. `b.age > a.age` under type
  hints) lowers through the segment predicate machinery into the subquery
  join's `ON` clause — the inner pipeline, aggregates included, still runs in
  the reference — and the correlation rule relaxed to reject only *rebinds*
  of the outer variable (pure references are honored by the reference seeds).
  Endpoint-only `shortestPath`/`allShortestPaths` lower to a recursive walk
  CTE with per-pair minimal-depth selection (SQLite-gated); `allShortestPaths`
  keeps tie multiplicity and `shortestPath` picks the reference's DFS-first
  path via a zero-padded edge-`rowid` sequence key. The oracle exposed and
  fixed an F10 reference bug: a no-`*` relationship inside `shortestPath`
  searched unbounded instead of exactly one hop. Oracle 20 differential
  tests.

- **PUSHDOWN2 PM2**: uncorrelated `CALL { … }` subqueries now push into
  backend SQL (`SubqueryReadPushdown`): a leading subquery lowers to its inner
  node scan, and `MATCH … CALL { … } …` lowers to a `LEFT JOIN ON 1=1` of the
  two scans — LEFT so an inner aggregate over an empty inner scan still
  produces its per-outer-row empty-group row, exactly like the reference. The
  inner pipeline, subquery-`RETURN` join, and outer tail run through the
  shared reference; correlated shapes (including same-name shadowing) fall
  back conservatively. Correlated `tvf.keys(n)` also pushes via a lateral
  `json_each` join (SQLite-gated). The oracle work exposed and fixed a latent
  reference bug: `DISTINCT` over computed `WITH`/subquery-`RETURN` items
  errored ("variable not bound") because dedup re-evaluated pre-projection
  expressions against post-projection rows; dedup now keys on the produced
  rows' values. Oracle +2 differential tests.

- Started the **PUSHDOWN2 goal** (`docs/GQL_PUSHDOWN2_GOAL.md`): PM1 done.
  Catalog procedures now push into backend SQL as a `ProcedureReadPushdown`
  leaf — `db.labels`/`db.relationshipTypes` as `SELECT DISTINCT` scans on both
  dialects, `db.propertyKeys` via SQLite `json_each`, and `tvf.range` with
  constant/parameter arguments via a guarded SQLite recursive CTE — with
  `YIELD`/`WHERE`/pipeline tails running through the shared reference so
  results stay byte-identical by construction. Dialect-gated row sources are
  reported through the new `ReadPushdown::supported_by`, and Sail falls back
  to the reference for them. The P0 fallback-pinning test found and fixed a
  bug where F10's `shortestPath(…)` wrapper was not rejected by the pushdown
  lowerers (a bare wrapped var-length pattern lowered as a plain var-length
  scan, returning wrong rows on Sail). Differential-oracle coverage grows by
  two tests over the embedded `turso` and real-SQLite engines.

## 0.12.1 "Shrimp" - 2026-08-06

Shrimp was a scoped crates.io patch, not a lockstep workspace release. It
published `grust-core`, `grust-cypher`, `grust-memory`, `grust-sail`,
`grust-sql-core`, `grust-turso`, and the `grust-graph` facade at 0.12.1 for the
graph-commit and Sail/Turso APIs consumed by Marciana. The other publishable
backend crates remained at 0.12.0, and no `v0.12.1` repository tag, Shrimp post,
TextPack, or 0.12.1 book was produced. Prawn is the first subsequent lockstep
workspace release and supplies those missing cross-workspace documentation and
verification boundaries without rewriting the historical registry state.

## 0.12.0 "Lobster" - 2026-07-03

Note: `0.12.0` widens public enums and structs (`Value::Graph`,
`GqlBackend::Falkor`/`Surreal`, new `GqlBackendDescriptor` and `CallClause`
fields), which is technically breaking for exhaustive matchers even within
`0.x`.

- Added **atomic Cypher transaction batches**: `CypherTransaction` accumulates
  eagerly-planned write statements between `START TRANSACTION`/`BEGIN` and
  `COMMIT` (with `READ ONLY` enforcement), and
  `execute_cypher_transaction_on_store` submits the whole batch in a single
  `apply_mutations` call — atomic on stores reporting
  `GraphMutationAtomicity::Transactional` (proven end-to-end on Turso, whose
  store wraps the slice in one `BEGIN…COMMIT` SQL transaction), and refused
  with a structured feature-tagged error on `OrderedNonAtomic` stores rather
  than silently committing non-atomically.
  `run_cypher_transaction_script_on_store` executes a full
  `BEGIN; …; COMMIT|ROLLBACK` script (lexer-aware statement splitting;
  `ROLLBACK` never touches the store). This closes the Unit 13 deferred tail;
  the `transaction-control` manifest summary now reflects executable
  atomicity.

- The **portable read corpus is now executable**: every case in
  `tests/gql/portable_read.json` (grown to 24 cases covering path/graph
  values, subqueries, TVFs, and shortest paths, including structured
  rejections) runs against the fixture graph and must match its expected
  outcome and error kind.

- **Full39075 is now the realized GQL profile** (Full39075 FM5): with F1–F11
  complete, every non-rejected feature in the manifest is `Supported` (69 of
  74; the other 5 are intentional strict-write rejections — conformance
  guards, not gaps). `docs/GQL_PROFILE_STATEMENT.md` now claims `Full39075` as
  the realized profile, `gql::tests::full_profile_claim_is_backed` pins the
  scoped-out set to exactly the five rejections, and the book chapter on the
  GQL layer is updated accordingly.

- Added **backend-native query passthrough** (Full39075 F11): the conformance
  spine gains `NativeQuery` / `NativeQueryLanguage` (cypher · sql · surrealql),
  a per-backend capability table (`GqlBackend::native_passthrough` + descriptor
  field), `ensure_native_passthrough` with structured feature-tagged
  non-support, and `native_passthrough_backends` reverse lookup. The backend
  catalog now includes **Falkor** and **Surreal** as `native-graph-backend`
  entries (Surreal honestly reports transactional atomicity). Executable
  escape hatches: `FalkorGraphStore::run_native_cypher` and
  `SurrealHttpGraphStore` / `SurrealSdkGraphStore::run_native_surrealql`
  (Sail's `query_arrow_ipc` already covered native SQL). All are deliberately
  outside portable conformance. `NativeCypherPassthrough` is now `Supported`:
  **every non-rejected manifest feature is implemented** (69 supported + 5
  intentional rejections).

- Added **shortest-path matching** (Full39075 F10): `MATCH p =
  shortestPath((a)-[:T*]->(b))` and `allShortestPaths(…)` over a single
  relationship segment now execute on the read reference. Per (start, end)
  endpoint pair the executor finds minimal-length simple paths by iterative
  lengthening over the bounded var-length enumerator; `allShortestPaths` keeps
  same-length ties, `shortestPath` returns the first in deterministic edge
  order. Endpoint, relationship-list, and path variables bind like the
  var-length machinery, and path variables return first-class `Value::Path`
  values. `ShortestPath` is now `Supported`; the candidate `Full39075`
  remainder drops to 1 planned feature + 5 intentional rejections.

- Added **table-valued functions** (Full39075 F9): `CALL name(args) [YIELD …]`
  now accepts argument expressions, evaluated against each incoming row
  (correlated TVFs), with the procedure's rows cross-joined onto the row
  stream. The registry keeps the nullary `db.*` catalog procedures (which now
  reject arguments with a structured error) and adds
  `tvf.range(start, end[, step]) YIELD value` and
  `tvf.keys(element_or_map) YIELD key`. `TableValuedFunction` is now
  `Supported`; the candidate `Full39075` remainder drops to 1 future + 1
  planned feature + 5 intentional rejections.

- Added **`CALL { … }` subqueries** (Full39075 F8) to the read reference
  executor: correlated import-all scoping (the subquery sees the outer row's
  bindings), WITH-style `RETURN` that preserves node/edge bindings for later
  `MATCH` extension, per-row execution (rows with empty subquery results are
  dropped, join semantics otherwise), `UNION`/`UNION ALL` arms, and structured
  rejections for column collisions, missing `RETURN`, and `RETURN *`.
  `Subquery` is now `Supported`; the candidate `Full39075` remainder drops to
  2 future + 1 planned features + 5 intentional rejections.

- Added **first-class graph values** (Full39075 F7): `grust_core::GraphValue`
  and `Value::Graph` model set-shaped graph values — construction deduplicates
  nodes by id and relationships by id-or-endpoint identity, preserving
  first-seen order for deterministic serialization. `GraphValue::from_graph` /
  `from_graph_parts` build graph values from snapshots, `Value::to_json` keeps
  the `{nodes, relationships}` shape, and the read reference executor gains a
  `graph(nodes, relationships)` constructor (e.g. over `collect(...)` lists)
  plus `nodes(g)` / `relationships(g)` accessors. `GraphValues` is now
  `Supported`; the candidate `Full39075` remainder drops to 3 future + 1
  planned features + 5 intentional rejections.

- Added the **Full39075 follow-on goal** (`docs/GQL_FULL39075_GOAL.md`) and
  landed F1 index-definition support: `cypher_ddl` / `sail_cypher_ddl` now parse
  portable single-property `CREATE INDEX name [IF NOT EXISTS] FOR ... ON (...)`
  and `DROP INDEX name [IF EXISTS]` DDL for node and relationship properties.
  `CypherConstraintRegistry` tracks named index metadata through
  `named_indexes()`, new public metadata types (`GraphIndexDefinition`,
  `GraphIndexElement`, `NamedGraphIndex`) are exported through `grust-cypher`,
  `grust-sail`, and the `grust-graph` facade, and `GqlBackendDescriptor` gains an
  `index_ddl` capability flag. `IndexDefinition` is now `Supported` in the GQL
  manifest; the candidate `Full39075` remainder drops to 8 future + 2 planned
  features + 5 intentional rejections.

- Added **graph-type definition DDL** (Full39075 F2): `cypher_ddl` /
  `sail_cypher_ddl` now parse portable `CREATE GRAPH TYPE name [IF NOT EXISTS]
  [OPEN|CLOSED] AS ...` and `DROP GRAPH TYPE name [IF EXISTS]` metadata. The
  first supported body surface covers `NODE Label (...)` and directed
  `EDGE Type FROM Source TO Target (...)` declarations with scalar/array field
  types and `REQUIRED` / `NOT NULL` markers, lowering to `GraphSchema` inside
  `GraphTypeDefinition`. `CypherConstraintRegistry` now tracks named graph types
  through `named_graph_types()`, and `GraphTypeDefinition` / `NamedGraphType` are
  exported through the language crate and facade. `GraphTypeDefinition` is now
  `Supported` in the GQL manifest; the candidate `Full39075` remainder drops to
  7 future + 2 planned features + 5 intentional rejections.

- Added **portable catalog metadata** (Full39075 F3): `CypherConstraintRegistry`
  can now materialize a `CypherCatalogSnapshot` for a named graph, carrying graph
  type, index, and named constraint metadata. `cypher_catalog_procedure` exposes
  deterministic read-only metadata tables for `db.graphs`, `db.graphTypes`,
  `db.indexes`, and `db.constraints`, and `GqlBackendDescriptor` gains a
  `catalog_metadata` capability flag. `CatalogMetadata` is now `Supported`; the
  candidate `Full39075` remainder drops to 6 future + 2 planned features + 5
  intentional rejections.

- Added **named graph selection** (Full39075 F4): the parser and semantic
  analyzer now recognize `USE <graph>` clauses, the Memory read reference path
  validates the selected graph before execution, and
  `run_read_query_on_named_graph` lets callers bind a single-graph snapshot to a
  non-default graph name. Catalog-backed callers can validate graph names through
  `ensure_catalog_graph_selection`, and `GqlBackendDescriptor` gains a
  `named_graph_selection` capability flag. `NamedGraphSelection` is now
  `Supported`; the candidate `Full39075` remainder drops to 5 future + 2 planned
  features + 5 intentional rejections.

- Added **session control** (Full39075 F5): `CypherSession` tracks the current
  graph and portable session settings, while `SessionCommand::parse` /
  `SessionCommand::apply` handle standalone `USE`, `SET name = literal`,
  `RESET name`, and `RESET ALL` commands. `USE` can validate against a
  `CypherCatalogSnapshot` before changing session state, and transaction-control
  behavior remains unchanged. `GqlBackendDescriptor` gains a `session_control`
  capability flag. `SessionControl` is now `Supported`; the candidate
  `Full39075` remainder drops to 5 future + 1 planned feature + 5 intentional
  rejections.

- Added **first-class path values** (Full39075 F6): `grust_core::PathValue` and
  `Value::Path` now represent fixed-length path bindings directly while
  `Value::to_json` preserves the existing `{nodes, relationships}` serialization
  shape. Returning a path variable now yields `Value::Path`, and existing
  `nodes(p)`, `relationships(p)`, and `length(p)` behavior remains compatible.
  `PathValues` is now `Supported`; the candidate `Full39075` remainder drops to
  4 future + 1 planned feature + 5 intentional rejections.

## 0.11.0 "Crab" - 2026-06-26

- **Turso MVCC + concurrent writes:** `TursoConfig` gains a `journal_mode: TursoJournalMode` field (`Wal` default, or `Mvcc`). `Mvcc` enables Turso's multi-version concurrency control via `PRAGMA journal_mode = mvcc` on connect — a database-*header* mode, so it only applies to a fresh database (an existing WAL database can't be converted; `connect` verifies the mode and errors otherwise). In MVCC mode, data writes (`put_node`/`put_edge`/`put_graph`/`delete_*`/`apply_mutations`) run inside a `BEGIN CONCURRENT … COMMIT` transaction with bounded retry on write-write/busy conflicts, so concurrent writers make progress; WAL-mode behavior is unchanged. Verified end-to-end: mode reported as `mvcc`, `BEGIN CONCURRENT` accepted, batch round-trips, and two concurrent writers writing overlapping keys both succeed via retry.

- **Profile statement (Unit 16):** added `docs/GQL_PROFILE_STATEMENT.md` — the precise, backed statement of the realized GQL/Cypher profile (58 of 74 catalogued features `Supported`) with every not-yet-supported feature explicitly enumerated and given a rationale, so the candidate `Full39075` claim is never silently unbacked. A new `full_profile_claim_is_backed` test pins the scoped-out set (8 future + 3 planned + 5 intentional rejections) to the manifest, so flipping any feature status forces the doc to be updated in lockstep.

- **Write widening (Unit 10b, W1/W2/W3):** a `MATCH … CREATE/MERGE` clause may now carry **multiple comma-separated relationship patterns** in one statement (`… CREATE (a)-[:R]->(b), (b)-[:S]->(c)`), each planned in order (W1); **incoming `<-[:T]-` edge writes** are accepted, normalized to the arrow's source→destination (W2); and **cross-variable correlated `SET`** (`MATCH (a)-[:R]->(b) SET a.x = b.y + 1`, and the cartesian `MATCH (a),(b) …` form) is supported via a new `GraphMutationPlanOp::SetMatchingNodeFromNode` executed by the Memory reference backend (other backends reject explicitly) (W3). Single-pattern / outgoing / single-target writes stay byte-identical (golden-guarded). Generated-id-by-default (W4) was intentionally **not** changed — generated ids remain opt-in via `CypherNodeIdPolicy`. See `docs/GQL_U10b_WRITE_WIDENING_AUDIT.md`.

- **Write-path cutover (Unit 10a, decision B):** the writable-Cypher entrypoints now route *acceptance of the mutation grammar* through the new standards-conformant parser as a gate, narrowing the public accept-set to standard GQL/Cypher. The non-standard **DELETE-by-pattern** forms the legacy string planner accepted (`DELETE (:Person {id})`, `DELETE (:a)-[:R]->(:b)`) are now rejected — use `MATCH … DELETE <var>` instead. Plan *building* still runs through the legacy planner, so plan shapes stay byte-identical (guarded by `tests/golden/write_golden.json`); only the `RETURN` projection and cross-statement local-variable bindings are intentionally left to the legacy path (the gate is parse-only over each mutation statement, RETURN split off). The new parser also now accepts reserved keywords as property/map keys (e.g. `{order: 1, limit: 3}`), preventing an unintended accept-set regression. Strict-write tests using the non-standard forms were migrated to standard Cypher.

- Added the **transaction-control language surface + capability reporting** (Unit 13). `grust_cypher::transaction` recognizes standalone `START TRANSACTION [READ ONLY|READ WRITE]` / `BEGIN` / `COMMIT` / `ROLLBACK` commands (`TransactionCommand::parse`, returning `Ok(None)` for non-transaction input so query parsing still applies — the keywords are *not* reserved in the lexer, so `start`/`commit`/… remain usable as identifiers). Per-backend atomicity is reported honestly via `GqlBackend::transactional()` / the new `GqlBackendDescriptor::transactional` flag (Turso/Postgres/Postgres-PGQ report `Transactional`; Memory/Sail do not) and `transactional_backends()`. `TransactionControl` is now `Supported`; atomic *execution* (wrapping a batch through the backend store) is delegated and wired after the write-path cutover. `SessionControl` is `Planned`.

- Added first-class **decimal** and **duration** value types (Unit T). `grust_core` gains dependency-free `Decimal` (fixed-point `mantissa(i128) × 10^−scale`, mirroring SQL DECIMAL(38,s); lossless within 38 digits, value-normalized) and `Duration` (ISO 8601 month/day/second/nanos model), each with parse/canonical-display, serde (as canonical string), ordering, and checked arithmetic. `Value` gains `Decimal`/`Duration` variants with `Value::decimal`/`Value::duration` constructors and `as_decimal`/`as_duration`; every backend's value serialization handles them (canonical/ISO strings). The Cypher read executor adds `decimal(...)`/`duration(...)` constructor functions, lossless `+`/`-`/`*` decimal arithmetic (ints coerce exactly; floats route to the f64 path), duration `+`/`-`, and exact decimal/duration comparison & ordering in `WHERE`/`ORDER BY`. `TemporalValues`/`DurationValues`/`DecimalValues` are now `Supported`.

- Added read-only **catalog procedures** via `CALL [YIELD]` (Unit 14): `db.labels()`, `db.relationshipTypes()`, and `db.propertyKeys()` parse in the new pipeline and execute in the Memory read reference over a `Graph` snapshot, returning deterministically sorted, distinct values. Supports standalone `CALL db.labels()` (the YIELD shape becomes the result table) and `CALL … YIELD col [AS alias] [WHERE …]` feeding downstream `WHERE`/`RETURN`/aggregation. `ProcedureCall` is now `Supported` in the feature manifest; procedure *arguments* remain feature-tagged unsupported.

- Expanded the read-path scalar function registry (Unit 14) with unary math functions `sqrt`, `exp`, `ln`/`log`, `log10`, `sin`, `cos`, `tan` (numeric → Float, null-propagating), usable in `WHERE` and `RETURN`.

- Added a strict-write **golden-snapshot** regression harness (`grust-cypher/tests/write_golden.rs` + `tests/golden/write_golden.json`, Unit 10a): pins the current planner output (plan or rejection) for a 20-statement write corpus so any future write-path change is caught byte-for-byte.

- Added graph-type validation (`grust_cypher::graph_type`, Unit 11): the open-vs-closed graph-type distinction (`GraphTypeMode`) and write-time type-violation checks `validate_node`/`validate_edge`/`validate_graph` over a `GraphSchema` — closed graph types reject undeclared labels/properties; both modes type-check declared properties and enforce required fields/constraints. Backend-neutral and additive (a `ValidateBeforeWrite` hook; changes no backend).

- Temporal values (`Value::DateTime`) now order chronologically (lexicographic over the RFC 3339 form) in both the read executor's comparison/`ORDER BY` and the RETURN projection ordering; previously any two datetimes compared equal. (Unit T, temporal.)

- Added a per-backend GQL/Cypher conformance model (`grust_cypher::gql`): `GqlBackend` + `GqlBackendDescriptor` + `GqlBackendRole`, with `backend_manifest()` and `cypher_conformance_backends()`. Honest capability flags (verified against the code): the executing Cypher-conformance set is Memory/Sail/Turso; only Sail has read pushdown; Postgres/pgGraph-PGQ are SQL/PGQ stores with no portable Cypher executor yet; helix/ladybug are internal (`publish=false`, out of facade); cocoindex is a sync target.

- Added backend-neutral read-query **pushdown** (`grust_cypher::pushdown`): a
  bounded `MATCH … RETURN` query's `MATCH`/`WHERE` filter is lowered into SQL via
  a `SqlDialect` (Spark and SQLite provided), while the `RETURN` projection runs
  through the shared Memory reference so pushdown results are identical to
  `grust_cypher::read::run_read_query` by construction. `SailGraphStore` gains a
  public `run_read_query` that pushes the filter into Spark SQL for the pushable
  subset (single node pattern with property comparisons) and falls back to the
  portable reference otherwise (additive public API). An embedded-SQLite
  differential oracle (`grust-turso`) verifies reference-vs-pushdown row equality
  without a server. The pushable subset now also covers a single **directed
  relationship segment** (`(a)-[:T]->(b)` / `<-[:T]-`, multiple rel types, inline
  endpoint/edge properties, and `WHERE` over `a`/`r`/`b`), lowered to a
  `grust_edges`/`grust_nodes` join; the backend returns the matched columns as
  text and `grust_cypher` reconstructs the bindings before projecting. A unified
  `plan_read` returns a `ReadPushdown` (single-query leaf or a `UNION`/`UNION ALL`
  of leaves, combined by `combine_union`). **`OPTIONAL MATCH`** (a mandatory node
  + one optional directed segment) lowers to a `LEFT JOIN` against a subquery for
  the optional segment, with null-padding (`r`/`b` → `null`) matching the
  reference. **Multi-pattern `MATCH`** (`(a)-[]->(b), (a)-[]->(c)` and bare cross
  products) lowers to a comma-join with shared variables reusing an alias. A
  **`WITH` horizon** (`MATCH … WITH … RETURN`) pushes the leading node scan/filter
  and runs the horizon (incl. aggregation) through the shared reference pipeline.
  This now
  covers **multi-segment paths** (`(a)-[]->(b)-[]->(c)`, chained joins) and
  **undirected** segments (`(a)-[]-(b)`, matched in either orientation), in any
  per-segment direction. **Variable-length** segments (`(a)-[:T*m..n]->(b)`, with
  an anonymous relationship) lower to a recursive CTE enumerating simple paths
  (no repeated nodes, like the reference); this is row-equality-verified against
  real SQLite and depends on recursive-CTE support in the target engine.
  `WHERE … IN [literals]` (and `NOT … IN`) is also pushed, on both the node and
  segment paths, for non-empty homogeneous int/float/string lists. `STARTS WITH`
  / `ENDS WITH` / `CONTAINS` with a non-empty string needle are pushed too
  (Spark `STARTSWITH`/`ENDSWITH`/`CONTAINS`, SQLite `instr`/`substr`), matching
  the reference for string-typed properties (a non-string value errors in the
  reference but filters under pushdown). Boolean equality (`prop = true|false`,
  `<>`) is pushed too (SQLite compares the `json_extract` integer `1`/`0`, Spark
  the `GET_JSON_OBJECT` text `'true'`/`'false'`). Arithmetic comparisons over
  typed numeric properties (`n.age + 1 > 40`) are pushed on the node and segment
  paths for the `+`/`-`/`*` subset (each property cast to its hinted type);
  `/` renders as floating-point division (reference `/` is f64); `%`/`^` and unknown-typed properties fall back (dialect-divergent). `ORDER BY` /
  `SKIP` / `LIMIT` are pushed into SQL on the single-node path for dialects whose
  JSON extraction is natively typed (SQLite/libSQL `json_extract`, not Spark
  `GET_JSON_OBJECT`), gated on no aggregate/`DISTINCT` and scan-var sort keys,
  with `NULLS LAST`/`FIRST` matching the reference; otherwise ordering stays in
  the reference projection. A `TypeHints` trait (built from the graph schema by
  the backend; `SailGraphStore` derives it from the applied `GraphSchema`) lets
  an untyped-JSON dialect like Spark push numeric `ORDER BY` too, by casting each
  sort key to its declared type. `ORDER BY`/`SKIP`/`LIMIT` pushdown also applies
  to the relationship-segment path (sort keys over `a`/`r`/`b`, including
  edge-property keys when the relationship has a single type the schema describes).
- Refactored `grust-cypher` from a single ~16k-line `lib.rs` and ~17k-line
  `tests.rs` into cohesive modules (`ddl`, `parse`, `primitives`, `planner`,
  `eval_rows`, `restricted_values`, `projection`, `where_clause`, `returning`,
  plus the new `gql`, `lexer`, `ast`, `parser`, `semantics`) and a per-area
  `tests/` directory. The public API is unchanged; crate internals are now
  `pub(crate)`.
- Tightened the `grust-sail` and `grust-graph` Cypher re-export surface
  (public-API change). `grust-sail` no longer re-exports all of `grust-cypher`
  via a glob — it now explicitly re-exports the portable Cypher API it executes.
  The `grust-graph` `sail` feature now enables `cypher`, and the facade
  re-exports the Cypher language surface once (from the `cypher` block) while the
  `sail` block re-exports only Sail-native items; this also fixes building the
  facade with `cypher` and `sail` enabled together. Removed dead
  `helix`/`ladybug` facade re-export blocks left over from those backends being
  dropped from the facade.
- Added `grust-postgres-pgq`, a PostgreSQL 19 SQL/PGQ backend that reuses the
  shared PostgreSQL universal-table store, creates a native `PROPERTY GRAPH`,
  executes bounded traversal through `GRAPH_TABLE`, and is exposed through the
  `grust-graph` facade feature `postgres-pgq`.
- Added Turso-backed matched-node patch execution for the Grust Cypher mutation
  executor. `TursoGraphStore` can now run the reusable Cypher
  `MATCH ... SET ... RETURN ...` path for bounded node patches while keeping
  unsupported matched edge/delete/update forms explicit.

## 0.10.0 - 2026-06-22

- Added `grust-sql-core`, a shared SQL generation crate for universal-table
  SQL backends, and refactored PostgreSQL/pgGraph and Turso lowering through
  it while keeping JSON operators, upsert syntax, view creation, transaction
  semantics, and bidirectional traversal join shapes dialect-specific.
- Added `grust-turso`, a Turso Rust SDK backend with local in-process Turso
  storage, optional Turso Cloud sync construction, universal node/edge tables,
  SQL-backed reads/traversal, schema views/indexes, and transactional mutation
  batches.

- Added a generic `grust-postgres` backend for extension-free PostgreSQL
  deployments such as Neon, with reusable `grust-postgres-core` storage,
  schema-view, traversal, and mutation SQL shared by `grust-pggraph`.
- Refactored `grust-pggraph` into a pgGraph extension/projection wrapper over
  the shared PostgreSQL backend implementation.
- Refreshed documentation status after the writable Cypher completion pass:
  updated book and Arrow examples for the `0.10.0` line, replaced the stale
  restart checkpoint, marked older backend proposal documents as historical
  design notes where implementation now exists, and added the next major
  Cypher work areas to `docs/CypherWrite.md`.
- Added `docs/GrustCypherFull.md` and `docs/GrustCypherBackends.md` to plan the
  path from the current strict Grust Cypher subset toward full GQL coverage and
  backend-specific portable conformance profiles.
- Split the full GQL plan into execution-sized logical work units with
  dependencies, full-access Codex estimates, and done criteria.
- Extracted the writable Cypher parser, planner, DDL types, constraint
  registry, return evaluator, and generic returning executor into a new
  `grust-cypher` crate, so any `GraphStore` backend can use the Cypher
  planning and materialization layer without depending on `grust-sail`.
  `grust-sail` retains the Sail SQL lowering, Arrow IPC staging, and
  SparkConnect execution and depends on `grust-cypher` for all Cypher types.
  The `grust-graph` facade exposes a new `cypher` feature that pulls in
  `grust-cypher` without requiring the full `sail` feature.
- Moved backend-neutral writable Cypher parser, planner, DDL, restricted
  returning, and Memory-backed generic execution tests from `grust-sail` into
  `grust-cypher`; `grust-sail` now keeps Sail SQL, Arrow, SparkConnect, and
  live Sail persistence coverage.
- Added a restricted boolean AST for mutating Cypher `MATCH ... WHERE`
  lowering, so bounded `AND` / `OR` / one-term `NOT` groups lower through one
  conservative backend-neutral predicate path and factored unparenthesized
  `AND` / `OR` groups can be accepted when they canonicalize to the existing
  foldable predicate-vector shape.
- Consolidated restricted writable Cypher aggregate projection materialization
  so literal, map/list, introspection, string, numeric, conversion,
  `coalesce`, `CASE`, and list-helper aggregate bodies reuse the scalar
  projection materializer while aggregate-specific `*`, whole-element,
  property, and path-function paths remain explicit.
- Consolidated restricted writable Cypher `COUNT(...)` projection
  materialization onto the same scalar projection classifier while preserving
  explicit `count(*)`, whole-element, direct-property, path-function, non-null,
  and `DISTINCT` semantics.
- Consolidated grouped writable Cypher aggregate row materialization so
  classifier-covered restricted scalar targets reuse the scalar projection
  evaluator while aggregate-specific `*`, whole-element, direct-property, and
  path-function paths remain explicit.
- Added an internal writable Cypher `RETURN` target materialization classifier
  that separates star, whole-element, direct-property, scalar-projection,
  element-function, and path-function targets before aggregate, grouped
  aggregate, and `COUNT` routing.
- Added an internal writable Cypher scalar projection kind classifier so
  restricted scalar evaluation now explicitly routes star, whole-element,
  direct-property, literal, map/list, conditional, coalesce, introspection,
  list-helper, numeric, conversion, string, element-function, and path-function
  target shapes.
- Added an internal writable Cypher scalar expression view so restricted scalar
  classification and evaluation route through expression-shaped variants rather
  than matching the public return-target enum directly.
- Added a dedicated internal evaluator boundary for writable Cypher restricted
  list-helper scalar expressions while preserving the existing list projection
  materializers and supported syntax.
- Added a dedicated internal evaluator boundary for writable Cypher restricted
  string-helper scalar expressions while preserving the existing string
  projection materializers and supported syntax.
- Added dedicated internal evaluator boundaries for writable Cypher restricted
  numeric and conversion scalar expressions while preserving the existing
  numeric, scalar cast, and list cast materializers and supported syntax.
- Added dedicated internal evaluator boundaries for writable Cypher restricted
  literal/composite, `CASE`/`coalesce`, and introspection scalar expressions
  while preserving existing materializers and supported syntax.
- Added dedicated internal evaluator boundaries for writable Cypher scalar
  binding routes and element/path wrapper routes, completing expression-family
  dispatch for the currently supported restricted scalar target shapes.
- Added an internal writable Cypher scalar AST-family classifier so the
  top-level scalar dispatcher routes through binding, wrapper, value, control,
  introspection, list, numeric, conversion, and string evaluator families.
- Promoted the internal writable Cypher restricted scalar expression view to a
  `CypherReturnScalarAst` boundary used by scalar kind classification, family
  classification, and scalar projection evaluation.
- Extended restricted writable Cypher `coalesce(...)` so arguments can be
  direct properties, literals, or already-supported restricted scalar targets
  evaluated through the scalar AST while still requiring one variable.
- Extended restricted writable Cypher list projections so list items can be
  direct properties, literals, or already-supported restricted scalar targets
  evaluated through the scalar AST while still rejecting nested list/map
  composites and cross-variable lists.
- Extended restricted writable Cypher map projections so entry values can be
  same-variable properties, literals, or already-supported restricted scalar
  targets evaluated through the scalar AST while still rejecting nested
  list/map composites and cross-variable values.
- Consolidated nested restricted scalar parsing across `coalesce(...)`, list
  projection items, and map projection values, including shared rejection for
  nested list/map composites before a broader expression AST exists.
- Extended restricted writable Cypher `CASE` branch values so `THEN` and
  `ELSE` can wrap same-variable direct properties, literals, or
  already-supported restricted scalar targets while preserving equality-only
  CASE predicates.
- Extended restricted writable Cypher list predicate equality values so
  `any` / `all` / `none` / `single` comparisons can use same-variable direct
  properties, literals, or already-supported restricted scalar targets while
  preserving property-only haystacks and item-variable equality predicates.
- Extended restricted writable Cypher `toLower(...)` and `toUpper(...)`
  projections so they can wrap direct properties, literals, or
  already-supported restricted scalar targets while preserving the existing
  string-only value semantics.
- Extended restricted writable Cypher `trim(...)`, `lTrim(...)`, and
  `rTrim(...)` projections so they can wrap direct properties, literals, or
  already-supported restricted scalar targets while preserving the existing
  string-only trim semantics.
- Extended restricted writable Cypher `reverse(...)` projections so they can
  wrap direct properties, literals, or already-supported restricted scalar
  targets while preserving the existing string-or-array reverse semantics.
- Extended restricted writable Cypher `isEmpty(...)` projections so they can
  wrap direct properties, literals, or already-supported restricted scalar
  targets while preserving the existing string, array, and JSON collection
  emptiness semantics.
- Extended restricted writable Cypher `split(...)` projections so their first
  argument can wrap direct properties, literals, or already-supported
  restricted scalar targets while delimiters remain non-empty string literals
  or parameters.
- Extended restricted writable Cypher `substring(...)` projections so their
  first argument can wrap direct properties, literals, or already-supported
  restricted scalar targets while offsets remain non-negative integer literals
  or parameters.
- Extended restricted writable Cypher `left(...)` and `right(...)` projections
  so their first argument can wrap direct properties, literals, or
  already-supported restricted scalar targets while lengths remain
  non-negative integer literals or parameters.
- Extended restricted writable Cypher `startsWith(...)`, `endsWith(...)`, and
  `contains(...)` projections so their first argument can wrap direct
  properties, literals, or already-supported restricted scalar targets while
  needles remain string literals or parameters.
- Extended restricted writable Cypher `replace(...)` projections so their
  first argument can wrap direct properties, literals, or already-supported
  restricted scalar targets while search and replacement strings remain
  literals or parameters.
- Extended restricted writable Cypher `toString(...)` projections so their
  argument can wrap direct properties, literals, or already-supported
  restricted scalar targets while preserving scalar-only string conversion.
- Extended restricted writable Cypher `abs(...)` projections so their argument
  can wrap direct properties, literals, or already-supported restricted scalar
  targets while preserving numeric-only absolute-value semantics.
- Extended restricted writable Cypher `ceil(...)` and `floor(...)` projections
  so their argument can wrap direct properties, literals, or already-supported
  restricted scalar targets while preserving numeric-only rounding semantics.
- Extended restricted writable Cypher `sign(...)` projections so their
  argument can wrap direct properties, literals, or already-supported
  restricted scalar targets while preserving finite numeric sign semantics.
- Extended restricted writable Cypher `toInteger(...)` and `toFloat(...)`
  projections so their argument can wrap direct properties, literals, or
  already-supported restricted scalar targets while preserving numeric and
  numeric-string conversion semantics.
- Extended restricted writable Cypher `toBoolean(...)` projections so their
  argument can wrap direct properties, literals, or already-supported
  restricted scalar targets while preserving boolean and boolean-string
  conversion semantics.
- Extended restricted writable Cypher `head(...)`, `last(...)`, and
  `tail(...)` projections so their argument can wrap direct properties,
  literals, or already-supported restricted scalar targets while preserving
  array-only list access semantics.
- Extended restricted writable Cypher list indexes and slice bounds so their
  subscript expressions can wrap direct properties, literals, or
  already-supported restricted scalar targets while preserving
  non-negative-integer subscript semantics.
- Extended restricted writable Cypher `toStringList(...)`,
  `toIntegerList(...)`, `toFloatList(...)`, and `toBooleanList(...)`
  projections so their argument can wrap direct properties, literals, or
  already-supported restricted scalar targets while preserving array-only list
  conversion semantics.
- Extended restricted mutating Cypher `MATCH ... WHERE` boolean lowering to
  collapse double negation over an otherwise bounded predicate back to the
  positive backend-neutral predicate.
- Extended restricted mutating Cypher `MATCH ... WHERE` `OR` folding to
  flatten nested parenthesized foldable `OR` terms before applying the
  existing same-property grouped predicate or grouped exclusion lowering.
- Extended restricted mutating Cypher `MATCH ... WHERE` boolean lowering so
  negated foldable `AND` groups, such as
  `NOT (n.status <> 'active' AND n.status <> 'pending')`, can lower through
  the existing same-property grouped predicate path, including matching string
  predicate groups such as
  `NOT (NOT n.name STARTS WITH 'Ad' AND NOT n.name STARTS WITH 'Gr')`, while
  mixed-property and general De Morgan cases remain rejected.
- Extended restricted mutating Cypher `MATCH ... WHERE` boolean lowering so
  duplicate negated `AND` terms such as
  `NOT (n.status = 'blocked' AND n.status = 'blocked')` collapse to the same
  bounded predicate as `NOT n.status = 'blocked'`.
- Extended restricted mutating Cypher `MATCH ... WHERE` string folding so
  nested negated `AND` groups can merge an already-grouped string predicate
  with another matching same-property string predicate while general boolean
  evaluation remains rejected.
- Extended restricted mutating Cypher `MATCH ... WHERE` factored-branch
  pruning so exact string predicates can be recognized as covered by sibling
  grouped string predicates over the same variable, property, and string
  operation family.
- Extended restricted mutating Cypher `MATCH ... WHERE` factored-branch
  pruning so negated string predicates can be recognized as covered by sibling
  grouped negated string predicates over the same variable, property, and
  string operation family.
- Extended restricted mutating Cypher `MATCH ... WHERE` factored-branch
  pruning so bounded predicates that imply `IS NOT NULL`, plus exact-null
  predicates that imply `IS NULL`, can be recognized as covered by sibling
  null-check predicates without reversing missing-property semantics.
- Extended restricted mutating Cypher `MATCH ... WHERE` factored-branch
  pruning so exact inequality predicates can be recognized as covered by
  equivalent singleton leading-`NOT` membership exclusions.
- Extended restricted mutating Cypher `MATCH ... WHERE` factored-branch
  pruning so singleton membership predicates can be recognized as covered by
  equivalent exact equality predicates.
- Canonicalized restricted mutating Cypher `MATCH ... WHERE` factored-branch
  pruning so equivalent singleton membership and exact equality branches keep
  the equality predicate form.
- Extended restricted mutating Cypher `MATCH ... WHERE` factored-branch
  pruning so ordered-bound predicates can be recognized as covered by sibling
  scalar inequality predicates when the excluded value cannot satisfy the
  bound.
- Extended restricted mutating Cypher `MATCH ... WHERE` factored-branch
  pruning so ordered-bound predicates can be recognized as covered by sibling
  grouped exclusion predicates when every excluded value cannot satisfy the
  bound.
- Extended restricted mutating Cypher `MATCH ... WHERE` simple `OR` lowering
  so non-folded bounded terms can reuse conservative branch subsumption, such
  as pruning a narrower string predicate when a sibling `IS NOT NULL` predicate
  already covers it.
- Extended restricted mutating Cypher `MATCH ... WHERE` negated simple `OR`
  lowering so a disjunction that first collapses to one bounded predicate can
  be inverted, preserving rejection for general De Morgan expansion.
- Extended restricted mutating Cypher `MATCH ... WHERE` negated factored `OR`
  lowering so a factored disjunction that first collapses to one non-empty
  bounded predicate can be inverted while broader De Morgan cases stay
  rejected.
- Extended restricted mutating Cypher `MATCH ... WHERE` negated `AND` lowering
  so the disjunction of negated bounded terms can reuse conservative branch
  subsumption when it collapses to one non-empty predicate.
- Extended restricted mutating Cypher `MATCH ... WHERE` negated simple `OR`
  lowering for same-property null disjunctions, producing bounded `IS NOT
  NULL` plus negated equality or membership predicates.
- Added `GraphNativeConstraintCapability` and
  `GraphStore::apply_native_constraint` to `grust-core` so backends can
  declare whether they support native index or native-enforcing constraint DDL
  for a given `GraphConstraint` and then handle explicit native DDL requests
  independently of `apply_schema`. The default implementation returns
  `Unsupported`, keeping Sail's read-before-write uniqueness honest until a
  backend-native unique constraint implementation exists.
- Implemented native graph constraint application for `MemoryGraphStore`:
  required and unique node or edge property constraints can now be explicitly
  applied, validated against the current graph, skipped with `if_not_exists`,
  and enforced on later writes without requiring typed `GraphSchema` metadata.
- Added `apply_cypher_native_constraints` in `grust-cypher` so parsed
  `CREATE CONSTRAINT` DDL can be applied directly through
  `GraphStore::apply_native_constraint`; the helper preserves
  `IF NOT EXISTS` semantics and rejects `DROP CONSTRAINT` until native drop
  semantics exist.
- Added a reusable LakeCat catalog-event graph projection helper in the
  `grust-graph` facade, covering event, warehouse, namespace, and table nodes
  with stable catalog containment edges.
- Added a LakeCat catalog graph adapter in the `grust-graph` facade that
  converts LakeCat `nodes`/`edges` envelopes into validated Grust graphs.
- Added `CypherConstraintRegistry`, `NamedGraphConstraint`, and
  `CypherDdlApplicationReport` for applying parsed Cypher constraint DDL to
  named schema metadata before projecting the resulting `GraphConstraint`
  values into `GraphSchema`, including `IF NOT EXISTS` and `IF EXISTS`
  reporting and atomic multi-statement registry application while keeping
  backend-native DDL and migrations deferred.
- Added `CypherConstraintRegistry::from_schema` and `apply_to_schema` so parsed
  Cypher constraint DDL can update a schema's constraint set while preserving
  existing node and edge type metadata.
- Fixed writable Cypher `RETURN` mutation report aggregation so precise
  insert/update counters are preserved when returning execution runs and merges
  per-operation mutation reports.
- Added `apply_cypher_ddl_to_schema` and `CypherSchemaApplication` as a small
  schema-management helper that parses Cypher constraint DDL, updates a
  `CypherConstraintRegistry`, projects the resulting constraints onto an
  existing `GraphSchema`, and calls `GraphStore::apply_schema`.
- Fixed `apply_cypher_ddl_to_schema` to stage registry changes until
  `GraphStore::apply_schema` succeeds, so backend schema-validation failures do
  not leave the caller's named constraint registry ahead of the applied schema.
- Added narrow writable Cypher `RETURN count(*)` support over the already
  materialized restricted write-result table, while still rejecting mixed
  aggregate and non-aggregate projections.
- Extended narrow writable Cypher count support to `COUNT(variable)` for
  variables bound by the write plan, including concrete and row-producing
  variables, while rejecting unbound count targets.
- Extended narrow writable Cypher count support to `COUNT(variable.property)`,
  counting only non-null projected values over the restricted materialized
  write-result table.
- Extended narrow writable Cypher count support to `COUNT(DISTINCT variable)`
  and `COUNT(DISTINCT variable.property)` over the restricted materialized
  write-result table, while keeping grouping and `COUNT(DISTINCT *)` deferred.
- Added restricted writable Cypher `RETURN` support for `SUM`, `AVG`, `MIN`,
  and `MAX` over `variable.property` projections already present in the
  materialized write-result table, including `DISTINCT` value deduplication and
  null/missing-value exclusion.
- Added restricted writable Cypher `RETURN collect(...)` support over
  variables and `variable.property` values already present in the materialized
  write-result table, returning a `Value::Json` array with optional
  `DISTINCT` value deduplication.
- Added restricted writable Cypher `RETURN collect(*)` support over the same
  materialized write-result table, returning JSON row objects keyed by bound
  variable name and supporting grouped collection.
- Added restricted writable Cypher `RETURN *` support over variables already
  bound by the write plan, expanding to deterministic element columns without
  adding arbitrary read-query projection semantics.
- Added endpoint-aligned row values for row-producing writable Cypher
  relationship writes, so matched source and destination variables can be
  returned alongside the produced relationship without independent node scans.
- Added restricted writable Cypher map projections such as
  `RETURN n { .id, .label }` over variables already bound by the write plan,
  now extended to allow literal, parameter, and same-variable property entries
  while keeping arbitrary map expressions deferred.
- Added restricted writable Cypher list projections such as
  `RETURN [n.id, n.label]` over one variable already bound by the write plan,
  now extended to allow literal and parameter items in the same restricted
  single-variable list while keeping arbitrary list expressions deferred.
- Updated the writable Cypher planning docs to reflect the post-review
  implementation status and the next continuation batches for backend-native
  constraints, shared write-result rows, and future expression slices.
- Added an explicit backend-native graph constraint DDL surface in `grust-core`
  through `GraphNativeConstraintCapability`,
  `GraphNativeConstraintRequest`, `GraphNativeConstraintReport`, and
  `GraphStore::apply_native_constraint`, keeping native constraint/index DDL
  separate from portable `GraphStore::apply_schema`.
- Added an explicit internal writable-Cypher write-result row model in
  `grust-sail` for row-node and row-edge values, centralizing restricted
  `RETURN` row-count validation and deterministic row-variable ordering for
  `RETURN *` and `collect(*)`.
- Added restricted writable Cypher `RETURN CASE WHEN variable.property =
  literal THEN literal ELSE literal END` scalar projections over the existing
  write-result row model while keeping general expression evaluation deferred.
- Extended restricted writable Cypher `RETURN CASE` projections to accept
  `CypherMutationOptions::parameters` in the equality value and literal branch
  positions.
- Added restricted writable Cypher aggregates over the existing restricted
  `CASE WHEN variable.property = literal THEN literal ELSE literal END`
  projection form, supporting `COUNT`, `SUM`, `AVG`, `MIN`, `MAX`, and
  `COLLECT` while preserving the literal-only CASE grammar.
- Added backend-neutral relationship numeric property updates for writable
  Cypher, lowering `MATCH ... SET e.key = e.key + literal_or_parameter` and
  the corresponding `-`, `*`, and `/` forms into explicit matched-edge
  read-modify-write mutation operations for Memory and Sail.
- Added strict multi-target `MATCH ... DELETE` support for relationship
  patterns such as `DELETE e, a`, lowering relationship deletes and
  ID-resolved endpoint node deletes into ordered Grust mutation operations.
- Added backend-neutral relationship-row deletes for writable Cypher, lowering
  broad endpoint targets and mixed forms such as `DELETE e, a` into captured
  `DeleteRelationshipRows` operations implemented by Memory and Sail.
- Aligned the Sail backend proposal and Cypher implementation plan with the
  current writable Cypher public contract, including the `grust-cypher`
  parser/planner split, restricted returning surface, native constraint helper,
  and relationship-row delete semantics.
- Added restricted writable Cypher path-shaped `RETURN` support for
  row-producing `MATCH ... CREATE/MERGE` relationship writes that bind a path
  variable such as `CREATE p = (n)-[r:TYPE]->(t)`, returning aligned source
  node, relationship, and target node JSON while keeping path properties and
  resolved-edge paths deferred.
- Added restricted writable Cypher path-shaped `RETURN` support for existing
  matched relationship rows updated by `MATCH p = (a)-[e:TYPE]->(b) SET ...`
  or `REMOVE ...`, reusing the same path JSON shape and row alignment as other
  write-result path returns.
- Added restricted writable Cypher path-shaped `RETURN` support for
  relationship-only matched deletes such as
  `MATCH p = (a)-[e:TYPE]->(b) DELETE e RETURN p`, returning the pre-delete
  path rows.
- Extended deleted relationship path returns to mixed relationship-row endpoint
  deletes such as `MATCH p = (a)-[e:TYPE]->(b) DELETE e, a RETURN p`,
  snapshotting endpoint nodes before the delete so returned paths can describe
  graph elements removed by the same operation.
- Extended path-bound mixed relationship deletes to explicit-ID endpoint
  targets by routing them through row snapshots, so
  `MATCH p = (a {id: ...})-[e:TYPE]->(b) DELETE e, a RETURN p` returns the
  pre-delete path while still deleting the resolved endpoint node.
- Extended restricted writable Cypher path-shaped `RETURN` support to
  `count(p)`, `count(DISTINCT p)`, and `collect(p)` over row-producing path
  variables, reusing the same aligned path materialization used by `RETURN p`.
- Extended restricted writable Cypher path-shaped `RETURN` support to resolved
  single-edge `MATCH ... CREATE/MERGE p = (a)-[r:TYPE]->(b)` writes, including
  `RETURN p`, `count(p)`, and `collect(p)` over the concrete path binding.
- Added restricted writable Cypher path introspection projections
  `length(p)`, `nodes(p)`, and `relationships(p)` for writable path variables,
  reusing the same path materialization as `RETURN p`.
- Extended restricted writable Cypher aggregates to accept path introspection
  projections such as `sum(length(p))`, `avg(length(p))`,
  `collect(nodes(p))`, and `collect(relationships(p))` over writable path
  variables.
- Extended restricted writable Cypher `COUNT` and `COLLECT` aggregates to
  accept the existing restricted map and list projection forms.
- Added restricted writable Cypher literal `RETURN` projections and aggregate
  bodies, including parameters in literal positions and `count(1)`,
  `count(null)`, `sum(1)`, `avg(1)`, and `collect('value')` over the existing
  materialized write-result table.
- Added restricted writable Cypher `coalesce(...)` projections and aggregate
  bodies over one bound variable's properties plus literal or parameter
  fallbacks, while keeping nested functions and cross-variable expression
  evaluation deferred.
- Added restricted writable Cypher `labels(node)` and `type(relationship)`
  projections and aggregate bodies over variables already bound by the
  materialized write-result table.
- Added restricted writable Cypher `properties(element)` and `keys(element)`
  projections and aggregate bodies over bound node and relationship variables,
  returning deterministic JSON values from Grust's stored property maps.
- Added restricted writable Cypher `startNode(relationship)` and
  `endNode(relationship)` projections and aggregate bodies over bound
  relationship variables, materializing endpoint nodes through the existing
  writable result table.
- Added restricted writable Cypher `id(element)` and `elementId(element)`
  projections and aggregate bodies over bound node and relationship variables,
  reusing the existing physical identity projection semantics.
- Added restricted writable Cypher `exists(variable.property)` projections and
  aggregate bodies over bound node and relationship variables, returning
  booleans from the existing property materialization path.
- Added restricted writable Cypher `size(variable.property)` projections and
  aggregate bodies over bound node and relationship variables, returning
  lengths for string and array-like property values.
- Added restricted writable Cypher `variable.property[index]` projections and
  aggregate bodies over array-like property values with literal or parameter
  non-negative integer indexes.
- Added restricted writable Cypher `variable.property[start..end]` projections
  and aggregate bodies over array-like property values with literal or
  parameter non-negative integer bounds.
- Added restricted writable Cypher `needle IN variable.property` projections
  and aggregate bodies over array-like property values with literal or
  parameter scalar needles.
- Added restricted writable Cypher `any` / `all` / `none` / `single` list
  predicate projections and aggregate bodies over array-like property values
  with equality predicates against literal or parameter values.
- Added restricted writable Cypher `toStringList`, `toIntegerList`,
  `toFloatList`, and `toBooleanList` projections and aggregate bodies over
  array-like property values.
- Added restricted writable Cypher `head(variable.property)` and
  `last(variable.property)` projections and aggregate bodies over array-like
  property values.
- Added restricted writable Cypher `tail(variable.property)` projections and
  aggregate bodies over array-like property values.
- Added restricted writable Cypher `range(start, end[, step])` literal list
  projections and aggregate bodies with integer literal or parameter bounds.
- Added restricted writable Cypher `toLower(variable.property)` and
  `toUpper(variable.property)` projections and aggregate bodies over bound
  node and relationship variables, keeping string normalization explicit and
  type-aware.
- Added restricted writable Cypher `trim(variable.property)`,
  `lTrim(variable.property)`, and `rTrim(variable.property)` projections and
  aggregate bodies over bound node and relationship variables.
- Added restricted writable Cypher `substring(variable.property, start[, length])`
  projections and aggregate bodies with literal or parameter integer offsets.
- Added restricted writable Cypher
  `replace(variable.property, search, replacement)` projections and aggregate
  bodies with literal or parameter string search and replacement values.
- Added restricted writable Cypher `startsWith(variable.property, needle)`,
  `endsWith(variable.property, needle)`, and
  `contains(variable.property, needle)` projections and aggregate bodies with
  literal or parameter string needles.
- Added restricted mutating `MATCH ... WHERE variable.property IN [...]`
  predicate support, including list-valued parameters and one leading `NOT`,
  lowering membership checks through backend-neutral `GraphPropertyPredicate`
  operators.
- Added restricted mutating `MATCH ... WHERE` support for same-property
  equality `OR` groups by folding them into backend-neutral membership
  predicates while keeping general boolean expression trees deferred.
- Added restricted mutating `MATCH ... WHERE NOT (...)` support for those same
  same-property equality `OR` groups by folding them into backend-neutral
  membership exclusion predicates.
- Extended the restricted mutating `MATCH ... WHERE` `OR` fold to combine
  same-property equality and membership predicates into one backend-neutral
  membership predicate, including the matching negated exclusion form.
- Added restricted mutating `MATCH ... WHERE` support for same-property string
  predicate `OR` groups such as repeated `STARTS WITH`, `ENDS WITH`, or
  `CONTAINS`, lowering them to backend-neutral grouped string predicates.
- Extended the restricted mutating `MATCH ... WHERE` boolean grammar to factor
  positive `OR` branches whose `AND` groups share identical bounded predicates
  and differ by one foldable same-property predicate, while still rejecting
  unfactorable general boolean expressions.
- Extended that factored `OR`-of-`AND` lowering to allow common branch terms
  that are themselves foldable parenthesized `OR` groups, preserving the flat
  backend-neutral predicate vector.
- Canonicalized restricted mutating `MATCH ... WHERE` lowering by removing
  exact duplicate bounded predicates after parsing and `OR` folding while
  preserving deterministic predicate order.
- Canonicalized each candidate factored `OR` branch before branch comparison so
  duplicate bounded predicates inside a branch do not block otherwise valid
  `OR`-of-`AND` lowering.
- Canonicalized folded mutating `MATCH ... WHERE` `OR` groups by removing exact
  duplicate membership values or grouped string needles while preserving
  first-seen order.
- Canonicalized repeat same-property membership filters in mutating
  `MATCH ... WHERE` by intersecting representable positive `IN` predicates and
  unioning repeat `NOT IN` exclusions.
- Represented empty same-property positive membership intersections as one
  empty `IN` predicate, giving mutating `MATCH ... WHERE` a backend-neutral
  no-match filter without adding a new predicate operator.
- Canonicalized same-property equality and membership combinations in mutating
  `MATCH ... WHERE`, including equality selected by `IN`, equality excluded by
  `NOT IN`, conflicting equality, and `IN` minus `NOT IN`.
- Canonicalized same-property scalar inequality combinations in mutating
  `MATCH ... WHERE`, including equality conflicts, repeated `<>` exclusions,
  `IN` minus `<>`, and `NOT IN` plus `<>`.
- Canonicalized same-property ordered comparison ranges in mutating
  `MATCH ... WHERE`, keeping stricter lower or upper bounds and collapsing
  impossible ranges to empty `IN`.
- Canonicalized same-property equality plus ordered range predicates in
  mutating `MATCH ... WHERE`, keeping equality when it satisfies the range and
  lowering out-of-range equality to empty `IN`.
- Canonicalized same-property positive membership plus ordered range
  predicates in mutating `MATCH ... WHERE`, filtering `IN` lists to values that
  satisfy the range and lowering fully excluded lists to empty `IN`.
- Canonicalized each factored mutating `MATCH ... WHERE` `OR` branch with the
  same bounded-predicate pipeline used by top-level `AND`, allowing
  branch-local equality, membership, inequality, and range simplifications to
  expose a backend-neutral common-predicate plus same-property fold shape.
- Pruned impossible factored mutating `MATCH ... WHERE` `OR` branches after
  branch-local canonicalization, lowering single-survivor groups directly and
  all-impossible groups to the existing empty `IN` no-match predicate.
- Pruned subsumed factored mutating `MATCH ... WHERE` `OR` branches after
  canonicalization, so narrower conjunctions such as `(A AND B) OR A` lower to
  the broader backend-neutral predicate set.
- Extended factored mutating `MATCH ... WHERE` `OR` branch subsumption with
  conservative same-property predicate implication for equality, membership,
  negated membership, scalar inequality, and ordered-bound predicates.
- Extended factored mutating `MATCH ... WHERE` branch subsumption to prune
  stricter same-direction ordered bounds when a sibling branch already accepts
  the broader range predicate.
- Consolidated restricted writable Cypher `RETURN` parsing so scalar
  projections and aggregate bodies share one return-target recognizer for the
  existing literal, map/list, path-helper, introspection, string, numeric,
  conversion, `coalesce`, and `CASE` forms.
- Added restricted writable Cypher `left(variable.property, length)` and
  `right(variable.property, length)` projections and aggregate bodies with
  literal or parameter integer lengths.
- Added restricted writable Cypher `reverse(variable.property)` projections
  and aggregate bodies over string and array property values.
- Added restricted writable Cypher `split(variable.property, delimiter)`
  projections and aggregate bodies with non-empty literal or parameter string
  delimiters, returning JSON string arrays.
- Added restricted writable Cypher `isEmpty(variable.property)` projections
  and aggregate bodies over string, array, and JSON collection property
  values.
- Added restricted writable Cypher `toString(variable.property)` projections
  and aggregate bodies over scalar property values.
- Added restricted writable Cypher `abs(variable.property)` projections and
  aggregate bodies over numeric property values.
- Added restricted writable Cypher `ceil(variable.property)` and
  `floor(variable.property)` projections and aggregate bodies over numeric
  property values.
- Added restricted writable Cypher `sign(variable.property)` projections and
  aggregate bodies over numeric property values.
- Added restricted writable Cypher `toInteger(variable.property)` and
  `toFloat(variable.property)` projections and aggregate bodies over numeric
  and numeric-string property values.
- Added restricted writable Cypher `toBoolean(variable.property)` projections
  and aggregate bodies over boolean and boolean-string property values.
- Added restricted writable Cypher grouping for mixed scalar and aggregate
  `RETURN` projections, grouping only by scalar projections over the
  materialized write-result table and then applying the existing
  `ORDER BY`/offset/limit controls.
- Added restricted writable Cypher `RETURN` rows for broad
  `MATCH ... DELETE` node and relationship writes by capturing the matched
  rows before deletion and projecting those pre-delete values after execution.
- Added ignored live Sail regression coverage for broad
  `MATCH ... DELETE ... RETURN` node and relationship writes, covering the
  native returning path in addition to the Memory/Sail helper path.
- Added opt-in generated relationship IDs for row-producing
  `MATCH ... CREATE` edge writes through
  `CypherRelationshipIdPolicy::GenerateForRowCreate`, and for row-producing
  `MATCH ... CREATE/MERGE` edge writes through
  `GenerateForRowCreateAndMerge`, backed by
  backend-neutral `GraphRowEdgeIdPolicy` metadata and deterministic
  `generated_row_edge_id` generation shared by Sail and Memory.
- Added row-level `RETURN DISTINCT` support for writable Cypher's restricted
  materialized result tables, with deduplication applied before existing
  `ORDER BY`, `SKIP`, and `LIMIT` controls.
- Extended writable Cypher `RETURN ORDER BY` to accept returned projection
  expressions, such as `ORDER BY n.name` when `n.name AS name` is projected,
  while still rejecting non-returned expressions.
- Added `OFFSET` as a writable Cypher `RETURN` control synonym for `SKIP` over
  the restricted materialized result table.
- Added explicit relationship `id` support for row-producing
  `MATCH ... CREATE/MERGE` edge writes when the matched endpoint row set
  produces exactly one edge, while rejecting multi-row fan-out with one literal
  relationship id.
- Fixed generic writable Cypher returning execution so
  `collect_written_edge_identities` can report row-producing
  `MATCH ... CREATE/MERGE` edge identities instead of rejecting that plan shape.
- Added `LIMIT ALL` support to writable Cypher `RETURN` control clauses,
  matching the existing read-query spelling while preserving numeric `LIMIT`
  behavior.
- Added serde serialization support for Cypher constraint DDL helper types,
  including `CypherConstraintRegistry`, so callers can persist named
  constraint metadata outside backend-native schema storage.
- Added `CypherConstraintRegistry::to_json` and `from_json` convenience helpers
  for caller-owned named constraint metadata persistence with Grust error
  mapping.
- Added Sail-owned `save_cypher_constraint_registry` and
  `load_cypher_constraint_registry` helpers that persist named registry JSON in
  a `grust_cypher_constraint_registry` table while keeping native backend
  constraint/index DDL and migrations deferred.
- Added `CypherSchemaManager` to keep a `GraphSchema` and named Cypher
  constraint registry together while applying Cypher DDL through
  `GraphStore::apply_schema` with success-only state updates.
- Added precise insert-versus-update classification to `GraphMutationReport`
  through `node_inserts`, `node_updates`, `edge_inserts`, and `edge_updates`,
  populated during plan execution by backends that can distinguish create from
  replace (the in-memory executor, Sail resolved node/edge upserts, and Sail
  and Memory row-producing MERGE/CREATE edges); unresolved upsert-only paths
  continue to report through the existing `*_upserts` totals when the backend
  cannot classify the write outcome.
- Added `ORDER BY`, `SKIP`, and `LIMIT` support to the writable Cypher `RETURN`
  slice, applied as a stable post-materialization step shared by Sail and the
  backend-neutral Memory returning helper, while still rejecting grouping and
  path returns.
- Changed `SailGraphStore` to validate unique-property constraints before writes
  through a read-before-write existence check in `put_node`, `put_edge`, and
  `put_graph`, and to report `ValidateBeforeWrite` instead of metadata-only for
  node and edge uniqueness.
- Added Cypher schema (DDL) parsing through `sail_cypher_ddl` and
  `sail_cypher_constraints`, turning `CREATE CONSTRAINT` and `DROP CONSTRAINT`
  statements into backend-neutral `CypherDdlStatement` / `GraphConstraint`
  values for node and edge uniqueness and `IS NOT NULL`, kept separate from the
  data-mutation plan and rejecting composite/node-key and index DDL.
- Added a batched `GraphStore::get_nodes` override for `SailGraphStore` that
  reads all requested ids in one `IN (...)` query instead of one round trip per
  id, matching the input-order, duplicate, and skip-missing default contract.
- Changed the Sail writable-Cypher scanners to share a single quote-aware
  `scan_unquoted` helper and changed the four fully-static degree SQL builders
  to return `&'static str` instead of allocating a `String` per call.
- Added a strict first writable Cypher `RETURN` slice for Sail through
  `CypherMutationTableResult` and `CypherResultTable`, allowing final
  property projections over node variables and concrete relationship variables
  already resolved by the write plan, including concrete edge upserts and edge
  patches, while keeping mutation reports count-oriented and rejecting
  aggregation, paths, ordering, limiting, broad matched-row result tables, and
  arbitrary read-query features.
- Fixed `MemoryGraphStore` to preserve parallel edges when they carry distinct
  explicit edge IDs, so the deterministic test backend matches Grust's
  identity model for id-bearing multi-edges.
- Fixed Sail matched relationship deletes to delete by the persisted
  `edge_key` selected by the relationship match, preserving sibling parallel
  edges when an explicit edge ID narrows the match.
- Added strict `CREATE` conflict checks to the generic writable Cypher
  `RETURN` helper for concrete node and edge writes, keeping row-producing
  edge strict checks backend-specific.
- Fixed strict writable Cypher `CREATE` preflight to reject duplicate concrete
  node or edge identities inside the same planned batch before any writes run.
- Added `n.label` and `e.label` projections to the strict writable Cypher
  `RETURN` slice for concrete bound node and relationship variables.
- Added concrete bound node and relationship element projections such as
  `RETURN n AS node, e AS relationship`, returned as `Value::Json` using the
  existing Grust `Node` / `Edge` serde shape.
- Added Sail writable Cypher `RETURN` rows for row-producing
  `MATCH ... CREATE/MERGE` relationship variables such as
  `RETURN e.label, e.source`.
- Added the same row-producing relationship `RETURN` support to the
  backend-neutral Memory/Sail returning helper for upsert-compatible execution.
- Added portable writable Cypher `RETURN` rows for restricted broad node
  `MATCH ... SET/REMOVE` writes, so the Memory/Sail returning helper can return
  post-write projections such as `RETURN n.id, n.seen` for matched node rows.
- Added portable writable Cypher `RETURN` rows for restricted broad
  relationship `MATCH ... SET/REMOVE` writes, returning post-write projections
  such as `RETURN e.id, e.seen` for matched edge rows.
- Fixed writable Cypher `RETURN` parsing so aliases such as `AS limit` and
  `AS skip` no longer trip the `LIMIT` / `SKIP` clause rejection.
- Added backend-neutral graph constraint metadata for required and unique node
  or edge properties, plus constraint capability reporting so backends can
  distinguish metadata-only constraints from validate-before-write behavior.
- Added portable unique-property validation to `GraphSchema::validate_graph`
  and wired the memory backend to reject duplicate unique node or edge
  properties before writes when a schema is applied.
- Added opt-in Sail writable Cypher node and edge identity payloads through
  `CypherMutationOptions::collect_written_node_identities`,
  `CypherMutationOptions::collect_written_edge_identities`,
  `CypherMutationResult::written_node_identities`, and
  `CypherMutationResult::written_edge_identities`, covering explicit and
  generated node writes plus resolved and row-producing edge writes without
  changing the count-oriented mutation report.
- Added Sail writable Cypher support for comma-separated `MATCH ... SET`
  assignments, preserving source order across literal patches, map patches,
  remove-on-null compatibility, and numeric node property updates.
- Added row-producing Sail writable Cypher `MATCH ... MERGE` for edges whose
  endpoints come from matched node variables, reusing the row materialization
  and backend-neutral execution path introduced for row-producing
  `MATCH ... CREATE`.
- Fixed Sail writable Cypher edge/node pattern classification so `->` inside a
  string literal no longer misclassifies a node pattern as an edge pattern.
- Added row-producing Sail writable Cypher `MATCH ... CREATE` for edges whose
  endpoints come from matched node variables, with backend-neutral planning,
  Sail and Memory execution, strict-create conflict checks, and ignored live
  Sail coverage for zero-, one-, and many-row creates.
- Added a bounded writable Cypher `MATCH ... WHERE` predicate grammar for Sail,
  lowering `AND`-joined property comparisons into backend-neutral
  `GraphPropertyPredicate` values that Memory can evaluate and Sail can lower
  to SQL, now including one leading `NOT` before a supported comparison and
  explicit `IS NULL` / `IS NOT NULL` property checks, with parentheses around
  supported predicate terms and `AND` groups, and restricted string predicates
  using `STARTS WITH`, `ENDS WITH`, and `CONTAINS`.
- Added opt-in strict `CREATE` execution for Sail writable Cypher through
  `CypherMutationOptions` and `CypherCreateMode::ErrorIfExists`, preserving the
  default upsert-compatible path.
- Added backend-neutral node patch mutations and Sail writable Cypher lowering
  for strict `MATCH ... SET n += { ... }` node map patches.
- Added cardinality-aware Sail writable Cypher planning and execution for broad
  node `MATCH ... DELETE`, including matched-row and changed-element mutation
  report fields plus ignored live Sail cascade coverage.
- Polished Sail writable Cypher parsing with case-insensitive top-level
  mutation keywords and comment stripping outside string literals.
- Added structured Cypher error variants for syntax, unresolved identity,
  unsupported cardinality, and execution failures while keeping execution
  Sail-specific over backend-neutral mutation plans.
- Added backend-neutral matching-node patch planning and Sail execution for
  broad node `MATCH ... SET n += { ... }`, including matched-row reporting and
  typed-node mirror updates through the existing node load path.
- Added backend-neutral edge patch mutations and Sail lowering for ID-resolved
  `MATCH ... SET e += { ... }`, with typed-edge mirror updates through the
  existing edge load path.
- Added Sail writable Cypher lowering for literal property assignment and
  explicit `REMOVE` on resolved node and edge identities, backed by
  backend-neutral property remove mutations and existing patch/load paths.
- Added backend-neutral matching-node property removal plus Sail and Memory
  execution for broad node `MATCH ... SET n.key = value` and
  `MATCH ... REMOVE n.key`, preserving literal-only assignment and matched-row
  reporting.
- Added Sail writable Cypher planning for resolved edge
  `MATCH ... CREATE`, reusing explicit-ID endpoint bindings and preserving
  strict `CREATE` intent for execution options.
- Added backend-neutral relationship match descriptors plus Sail and Memory
  execution for broad relationship `MATCH ... DELETE`, `SET`, and `REMOVE`
  mutations over endpoint label/property predicates and optional edge `id`.
- Extended relationship match descriptors to carry relationship property
  predicates beyond `id`, with Sail SQL lowering and Memory execution for
  broad relationship delete, patch, assignment, and removal.
- Added Sail writable Cypher parameters through
  `CypherMutationOptions::parameters`, limited to literal positions such as
  IDs, property maps, and literal property assignments.
- Added minimal Sail writable Cypher numeric node property updates such as
  `MATCH (n:Counter {id: 'c1'}) SET n.count = n.count + 1`, lowering through
  backend-neutral read-modify-write mutation plans shared by Sail and Memory.
- Added `CypherNullAssignment` and
  `CypherMutationOptions::null_assignment` so callers can opt into
  Cypher-compatible `SET x.key = null` property removal while preserving
  `Value::Null` storage by default.
- Added opt-in generated node IDs for Sail writable Cypher node `CREATE`
  through `CypherNodeIdPolicy::GenerateForCreate` and
  `CypherMutationResult::generated_node_ids`, while keeping explicit IDs as the
  default and preserving resolved edge endpoint requirements.
- Added the backend-neutral `CypherMutationExecutor` plan-execution facade and
  implemented it for Sail and Memory, allowing Sail-planned writable Cypher to
  execute deterministically on the in-memory backend.
- Added `GraphMutationAtomicity` as an optional mutation-batch capability marker
  and tests documenting default ordered/non-atomic partial-failure behavior.
- Added an internal Sail writable-Cypher parser front-door that classifies
  top-level mutation statements before lowering while preserving the existing
  Sail-owned parser.

## 2026-06-15 - 0.8.4

- Extended strict writable Cypher planning in `grust-sail` with ID-resolved
  `MATCH ... DELETE` for single node or edge patterns.
- Added ID-resolved `MATCH ... MERGE` edge planning, allowing explicit-ID node
  matches to bind variables used by one relationship `MERGE`.
- Documented the remaining writable Cypher completion batches in
  `docs/CypherWrite.md`.

## 2026-06-14 - 0.8.3

- Extended strict writable Cypher planning in `grust-sail` to accept ordered
  multi-statement mutation batches and aggregate mutation reports across the
  whole batch.
- Added local node variable binding for writable Cypher batches, allowing
  explicit-ID node patterns to bind variables and later edge or delete patterns
  to reuse those variables while rejecting unbound references and conflicting
  rebinding.

## 2026-06-14 - 0.8.2

- Added backend-neutral `GraphMutationPlan`, `GraphMutationPlanOp`, and
  `GraphMutationReport` types in `grust-core` for resolved graph mutation
  planning.
- Added strict v1 writable Cypher support in `grust-sail`, including
  `sail_cypher_mutation_plan` and `SailGraphStore::execute_cypher_mutation`.
  The v1 subset supports explicit-ID node `CREATE`/`MERGE`, resolved endpoint
  edge `CREATE`/`MERGE`, and resolved node/edge `DELETE` through existing
  `GraphMutationStore` semantics.
- Added unit tests and an ignored live Sail integration test for writable
  Cypher planning and execution.

## 2026-06-14 - 0.8.1

- Added Sail Delta table properties for typed graph tables, marking generated
  node and edge tables with `grust.graph.kind` and `grust.graph.label`
  metadata for downstream planners.
- Added public Sail constants for graph table property names and values.
- Added an ignored live Sail test covering Cypher `MATCH` over Grust backend
  tables, including outgoing, incoming, undirected, and `LIMIT ALL` query
  forms.

## 2026-06-14 - 0.8.0

- Added `GraphIndex` to `grust-core` as a shared dense adjacency layer for
  local analytics, backend planning, and adapters that need validated edge
  endpoint indexes.
- Added a dependency-free `benchmarks` example in `grust-graph` with ring,
  grid, layered DAG, clustered, Graph500-style R-MAT, and GAP-style R-MAT graph
  families for core graph/index operations.
- Added Sail graph analytics helpers for reading the persisted generic graph
  tables and computing in-degree, out-degree, total degree, and directed degree
  pairs through Spark SQL.
- Added public Sail table/column contract helpers for generic and typed graph
  planning, including field projection helpers shared with GrustFrames-style
  lowerings.
- Added Sail typed-table descriptors and directional triplet SQL helpers for
  GrustFrames-style triplet filters, motifs, and aggregate-message lowerings.
- Changed Sail generic edge persistence to keep staged `edge_key` and optional
  explicit edge `id` columns in `grust_edges`, so read-back and external
  planners can preserve stable edge identity.
- Changed structural `edge_key` construction to preallocate and append instead
  of using `format!`, reducing allocation overhead in graph-index and benchmark
  paths.

## 2026-06-13 - 0.7.2

- Extended `grust-ladybug` to expose Ladybug typed and untyped graph modes
  explicitly through `LadybugGraphMode`, `LadybugConfig::typed`, and
  `LadybugConfig::untyped`.
- Changed `grust-ladybug` to preserve an applied `GraphSchema` and validate
  later node, edge, and graph writes against it, while keeping untyped dynamic
  graph writes as the default mode.
- Changed Ladybug `clear` to recreate applied schema tables so typed-mode
  stores remain ready for validated writes after reset.
- Updated README, the Ladybug backend proposal, the Grust book, and the
  overview blog to describe Ladybug as supporting both typed and untyped graph
  usage rather than only schema-first usage.

## 2026-06-13 - 0.7.1

- Added Arrow IPC data-source support for `grust-ladybug`, including embedded
  Ladybug node-table, relationship-table, CSR relationship-table, Arrow query,
  and Arrow table drop helpers behind the `arrow` feature.
- Added `grust-graph`'s `ladybug-arrow` facade feature so applications can
  enable embedded LadybugDB Arrow support through the main package.
- Added Sail Arrow IPC APIs for staging arbitrary Arrow streams as session temp
  views, collecting Spark SQL results as Arrow IPC chunks, and loading
  Grust-shaped node/edge IPC streams through the normal graph write path.
- Documented the Arrow IPC boundary in `docs/Arrow.md`, including why Grust
  avoids requiring one exact Rust `arrow` crate version across Ladybug and Sail.

## 2026-06-13 - 0.7.0

- Added `grust-ladybug`, an embedded LadybugDB backend using the Rust `lbug`
  crate directly for schema-backed graph writes, reads, and traversal.
- Proposed `grust-ladybug` as a schema-first embedded LadybugDB backend, with
  notes on storage layout, `lbug` integration, traversal lowering, and testing.

- Added `#[must_use]` diagnostics to graph builder completion methods so
  accidentally discarded builder results warn at compile time.
- Added `cocoindex_export_to_graph` so CocoIndex target-state JSON can be
  loaded back into Grust graphs.
- Changed the `grust-graph` memory facade and prelude exports to re-export the
  full `grust-memory` crate surface, matching other backend feature exports.
- Expanded CocoIndex adapter coverage for zero-edge exports, missing source
  nodes, explicit edge IDs, and non-finite float export errors.
- Documented the portable `PutOutcome` and `GraphSchema::apply_schema`
  contracts so backend-specific upsert and schema-enforcement behavior is
  explicit.
- Changed `Value::DateTime` to store an opaque validated `RfcDate`, including
  validating serde deserialization for tagged date-time values.
- Removed the unused `id` field from `GraphMutation::DeleteEdge`; edge deletes
  are represented by `(from, label, to)`.
- Replaced per-operation FalkorDB Redis connection creation with a reusable
  connection pool.
- Changed Sail read filters to pass Spark Connect named arguments instead of
  inlining literals into SQL text, and changed Sail deletes to stage values in
  Arrow temp views before running argument-free SQL commands.
- Changed FalkorDB schema and write paths to share the canonical lower_snake
  schema identifier normalizer for node labels.
- Expanded SurrealDB response-parser unit coverage across string, object,
  typed-object, and backtick-quoted record ID shapes.

## 2026-06-13 - 0.6.8

- Added typed readback helpers: `TypedNode::from_node`,
  `TypedNode::from_node_with`, `TypedEdge::from_edge`, and
  `TypedEdge::from_edge_with`.
- Preserved existing typed `id` properties during `TypedGraphBuilder` lowering
  so domain IDs can round-trip through stored Grust nodes.
- Added typed round-trip tests through `MemoryGraphStore`.

## 2026-06-13 - 0.6.7

- Documented that the default `GraphMutationStore::apply_mutations`
  implementation is ordered but non-atomic.
- Added transactional `apply_mutations` overrides for pgGraph and SurrealDB so
  mutation batches are wrapped in backend transactions.
- Added pgGraph mutation support and SurrealDB HTTP/SDK mutation support for
  node deletes, edge deletes, and ordered mutation batches.

## 2026-06-13 - 0.6.6

- Replaced LanceDB `Start::NodesByProperty` JSON substring matching with exact
  property comparison after reading label-filtered rows, avoiding false
  positives from nested JSON or serialized property fragments.

## 2026-06-13 - 0.6.5

- Changed SurrealDB generic edge reads to return a clear configuration error
  when `SurrealConfig.relationships` is empty, instead of silently returning no
  edges from an empty table scan.
- Preserved explicit SurrealDB edge-label reads without requiring
  `SurrealConfig.relationships`, so callers can still query a known relation
  table directly.

## 2026-06-12 - 0.6.4

- Added `GraphStore::get_nodes` as an additive batch-read API with a default
  repeated-`get_node` implementation.
- Added native `get_nodes` overrides for memory, LanceDB, pgGraph, and
  SurrealDB stores.
- Updated LanceDB and SurrealDB traversal paths to batch target-node reads per
  traversal step instead of issuing one node read per traversed edge.

## 2026-06-12 - 0.6.3

- Preserved supported non-string properties in Helix node and edge writes
  instead of silently dropping them; unsupported JSON object properties now
  return an explicit error.
- Moved shared relationship-type and structural edge-key helpers into
  `grust-core`, reducing duplicated backend lowering logic.
- Tightened pgGraph JSON property-key validation so generated JSONB
  expressions only accept safe identifier-shaped keys.
- Simplified SurrealDB HTTP authentication through reqwest's Basic auth helper
  and selected the SurrealDB SDK namespace/database once at connection time.
- Added `docs/INTEGRATION.md` as the contributor-facing guide for backend
  integration tests, including Docker, source-checkout, quick, full, and CI
  workflows.
- Added integration-test launcher profiles:
  - `quick` for local LanceDB and CocoIndex checks;
  - `docker` for Docker-backed contributor runs;
  - `all` for the full maintainer matrix.
- Added launcher modes:
  - `auto` to prefer already-running services, then source checkouts, then
    Docker where available;
  - `docker` to avoid source checkouts and use Compose-backed services;
  - `source` to avoid Docker and use local backend checkouts.
- Added `scripts/integration-test.sh doctor` to report selected backends,
  startup mode, Docker availability, source checkout state, ports, and Docker
  image choices before a long integration run.
- Pinned contributor Docker images for reproducible integration runs while
  keeping `GRUST_INTEGRATION_IMAGE_CHANNEL=latest` as an explicit compatibility
  lane.
- Hardened pgGraph startup so an occupied PostgreSQL-compatible port is only
  reused if the `graph` extension is available; otherwise Docker-capable modes
  automatically start Grust's pgGraph container on a free fallback port.

## 2026-06-12 - 0.6.2

- Expanded the backend integration launcher to run the full backend family by
  default: Sail, SurrealDB, FalkorDB, HelixDB, LanceDB, CocoIndex, and pgGraph.
- Added pgGraph Docker coverage with the official
  `ghcr.io/evokoa/pggraph:0.1.7` image on host port `55432`, so the pgGraph
  integration test no longer depends on a manually installed local PostgreSQL
  extension.
- Added HelixDB live integration coverage through a disposable local Helix
  project started from the configured `~/src/HelixDB` checkout.
- Added explicit LanceDB and CocoIndex integration checks to the shared
  launcher, covering local LanceDB persistence/traversal and CocoIndex public
  export shape.
- Fixed HelixDB live read hydration for current Helix responses by reading
  nested `properties` payloads, `$id` node identifiers, and `$from`/`$to` edge
  endpoints.
- Fixed pgGraph table registration against the current extension API by passing
  node and edge tables as `regclass` values instead of plain text names.
- Updated README, the Grust book, and the overview blog so backend integration
  instructions describe the full real-test matrix instead of the earlier
  three-backend subset.

## 2026-06-12 - 0.6.1

- Added an explicit backend integration-test launcher:
  - `scripts/integration-test.sh`
  - `integration/backends.conf`
  - `docker-compose.integration.yml`
- Made live backend tests visible and intentional instead of silently passing
  when a service is absent. Live tests are now ignored in ordinary unit-test
  runs and exercised through the launcher.
- Configured the launcher to prefer local source checkouts for Sail,
  SurrealDB, FalkorDB, and HelixDB, with Docker Compose fallback for
  Docker-friendly backends.
- Added live FalkorDB and SurrealDB integration tests to complement the
  existing Sail live tests.
- Fixed Sail live-test reset behavior by dropping and recreating Delta tables,
  including typed schema tables, instead of relying on fragile deletes.
- Hardened Sail SQL execution for the current Spark Connect/Sail behavior by
  inlining validated literal arguments when server-side SQL parameters are not
  accepted.
- Kept Sail traversal joins keyed on globally unique node IDs so single-edge
  writes with unknown endpoint labels still traverse correctly.
- Fixed SurrealDB live traversal by:
  - running the live HTTP test inside a Tokio runtime;
  - ensuring bootstrap creates the generic `record` fallback table;
  - creating missing relation tables before idempotent relation upserts;
  - normalizing Surreal record keys such as ``person:`person-1` `` back to
    Grust node IDs.
- Updated README, Sail backend notes, the Grust book, book metadata notes, and
  the overview blog for the `0.6.1` release and current `GraphStore` return
  types.
- Rebuilt the Grust PDF, EPUB, MOBI, and version marker artifacts for `0.6.1`.

## 2026-06-12 - 0.6.0

- Released Grust `0.6.0`.
- Added the `GraphMutationStore` path for incremental upserts and deletes
  where a backend can support mutation semantics beyond replacement.
- Expanded `PutOutcome` and updated write paths so single-element writes can
  report inserted, updated, deduped, or backend-opaque upserted outcomes.
- Extended `Value` and `FieldType` with timestamp and numeric-array support,
  including validation for RFC 3339 datetime strings.
- Wired schema edge uniqueness and undirected endpoint validation through the
  core schema path.
- Improved schema validation performance by indexing node labels for edge
  validation.
- Tightened Sail correctness and safety:
  - traversal joins use node IDs instead of empty endpoint-label columns;
  - property keys and non-finite floats are rejected before SQL generation;
  - single-edge writes validate and mirror into typed edge tables;
  - Arrow IPC staging is used for bulk node and edge batches.
- Improved memory-store edge validation so `put_edge` no longer clones the
  whole graph for every edge.
- Updated book and blog artifacts for the release.

## 2026-06-11 - 0.5.0

- Released Grust `0.5.0`.
- Added schema-backed typed storage across the backend family:
  - memory validates schema-backed writes;
  - LanceDB mirrors labeled rows into typed Arrow tables;
  - pgGraph exposes typed SQL views and expression indexes;
  - Sail mirrors schema-labeled rows into typed Delta tables;
  - SurrealDB lowers schemas into `DEFINE TABLE` and `DEFINE FIELD`;
  - FalkorDB creates useful label/property indexes.
- Updated the Grust book and overview blog to describe typed ingestion,
  schema-backed writes, and backend-specific typed storage surfaces.
- Polished book artifacts, metadata, page numbering, and Kindle-facing EPUB
  packaging.

## 2026-06-10 - 0.4.0

- Published the Elmarit `0.4.0` line.
- Added the optional `typed-garde` feature and `TypedGraphBuilder`.
- Added typed graph examples that validate Rust structs with `garde` and lower
  them into normal Grust nodes and edges.
- Added typed ingestion tests for coexistence with raw graph values and
  validation failures before graph construction.
- Documented the typed graph-builder design and release workflow.
- Hardened and documented the Grust book publishing pipeline:
  - separate generated cover;
  - stable `grust.epub` output;
  - versioned Send to Kindle symlink;
  - metadata validation;
  - visible table of contents;
  - PDF page numbering that starts after the cover.

## 2026-06-10 - 0.3.0

- Prepared and released the `0.3.0` workspace under the `querygraph/grust`
  repository identity.
- Updated repository and crate metadata to use `https://github.com/querygraph/grust`.
- Added release workflow documentation, including dependency-order publishing
  and registry verification.
- Continued book publishing work in preparation for the Elmarit line.

## 2026-06-07 - 0.2.0

- Released Grust `0.2.0`.
- Added JSON, YAML, and XML graph document loading and saving.
- Updated the Grust book for graph document formats and the import/export
  story.
- Renamed the public facade package to `grust-graph` while keeping the Rust
  library name `grust`, so downstream imports can continue to use
  `use grust::prelude::*`.
- Added a separate book cover build.

## 2026-06-06 - 0.1.x Publication Preparation

- Prepared the workspace crates for publication.
- Added Apache-2.0 and MIT license files.
- Added repository, homepage, keyword, category, and description metadata to
  the publishable crates.
- Started aligning README examples and crate manifests for crates.io.

## 2026-06-05 - Book

- Added the first Grust architecture book under `docs/book`.
- Documented the shape of the core model, traversal IR, store contract,
  backend architecture, and future design direction.

## 2026-06-02 - CocoIndex Adapter

- Added `grust-cocoindex`.
- Exported Grust graphs into CocoIndex-style node and relationship target
  state.
- Preserved stable node keys, endpoint labels, and plain JSON properties in the
  export adapter.

## 2026-06-01 - Backend Expansion

- Added and documented the Sail Spark Connect backend.
- Added pgGraph backend work and design notes.
- Added the LanceDB backend.
- Moved unit tests into crate-local test files.
- Updated README and backend proposals to describe the new backend family.

## 2026-05-31 - 0.1.0

- Created the initial Grust workspace.
- Added the core property graph model, graph builder, traversal IR, store
  traits, public facade crate, and deterministic in-memory store.
- Added the first backend graph stores.
- Switched graph stores to async HTTP/client patterns where appropriate.

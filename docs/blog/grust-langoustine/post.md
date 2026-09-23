# Grust Langoustine: narrower graphs, cheaper accounting, and scores you can ask for in f32

Grust gives Rust applications one property-graph API across memory, embedded databases, SQL systems and remote graph services. Nodes, edges, typed identities, traversals, mutations, schema and graph algorithms are written once against that API; Memory, Sail/Spark, PostgreSQL, pgGraph, PostgreSQL SQL/PGQ, Turso, SurrealDB, FalkorDB, LanceDB and CocoIndex sit behind it, and each adapter states which operations it pushes down, runs natively, answers through the portable reference, or does not support. `grust-cypher` is the portable GQL/Cypher layer over the same model. Mysid 0.22.0 was about what those graphs can be asked. Langoustine 0.23.0 is about what asking costs.

See the [repository and API guide](https://github.com/querygraph/grust), the [Grust book](https://firstpair.org/read/grust/), the [GQL profile statement](https://github.com/querygraph/grust/blob/main/docs/GQL_PROFILE_STATEMENT.md) and the full [`CHANGELOG.md`](https://github.com/querygraph/grust/blob/main/CHANGELOG.md).

Nothing in this release changes an answer. Every kernel in it returns the same bits it returned in 0.22.0, at both score precisions and at every worker count, and the pinned digest tests that say so are unmodified. What changed is the memory a graph occupies, the work a sweep performs, and what the default accounting mode costs to have on.

## Scores in f32, if you ask for them

PageRank and ArticleRank can now compute in single precision. In Rust that is `pagerank_f32`, returning `PageRank<f32>`; `PageRank` became `PageRank<F = f64>`, so every existing caller compiles unchanged and `pagerank` still returns `PageRank<f64>`. One implementation serves both, generic over a sealed `Score` trait that only `f64` and `f32` implement. In Cypher, `grust.algorithms.pagerank` and `grust.algorithms.articleRank` take `precision: 'f64' | 'f32'`, defaulting to `'f64'` and refusing anything else; at `'f32'` the `score` column is Float32 on every batch, and `iterations`, `converged` and `residual` keep their types.

Every score, per-arc probability, dangling mass, teleport share and base is formed and accumulated in the score type. The L1 residual is still summed in `f64` from the differences at either precision — which is the arrangement `neo4j-labs/graph` uses for its f32 PageRank, so the two can be compared at one precision under one stopping rule.

Half the width is half the score arrays, and the pull holds three of them. But single precision is a decision with consequences, not a free switch, and the ones we found are worth stating before you flip it:

- **A tolerance below one f32 ulp of a moving score is met only at an exact fixed point.** On a four-node graph whose two largest scores sit near 0.45, one ulp is 2⁻²⁵ and the default tolerance of 1e-8 is below it: the residual is exactly 2⁻²⁴ for all 1000 iterations and `converged` comes back false. The test pins that behaviour rather than loosening the tolerance to hide it.
- **At tolerance zero, f32 reaches an exact fixed point sooner** — 147 iterations against f64's 261 on the 120,000-node fixture.
- **On a graph where most nodes are dangling, f32 needs more iterations**, about twice as many at every tolerance of 1e-6 and below on a fixture with half its 200,000 nodes dangling.

At the default 1e-8 on ordinary graphs the two track each other closely: on that 120,000-node, 600,000-arc fixture both stop at iteration 93, the f32 residual within a few percent of the f64 one.

## A projection that costs four bytes where it used to cost eight

A projection's packed adjacency is compressed sparse row: an array of row bounds, one per node plus a terminator, and an array of arc targets. Both were `usize`. Both are now `u32`, widened on every read through `#[inline(always)]` accessors or a typed slice. The fields are private, so every read in the crate was converted rather than silently widened.

The arithmetic, from the structures rather than from a benchmark:

| | before | now |
| --- | ---: | ---: |
| row bound, per node + 1, per CSR | 8 bytes | 4 bytes |
| outgoing arc, unweighted (target + original-edge slot) | 16 bytes | 12 bytes |
| outgoing arc, weighted (+ `f64` weight) | 24 bytes | 20 bytes |
| reverse arc, unweighted (target only, no edge slots) | 8 bytes | 4 bytes |
| reverse arc, weighted | 16 bytes | 12 bytes |

So an unweighted outgoing adjacency falls by a quarter, the transpose halves, and each CSR's row-offset array halves. `estimateCsr` and `projectionStats` report the narrower sizes, and the `CsrEstimate` fields are computed from exactly this table. On the four-node, three-edge undirected Cypher fixture the reported `csrBytes` falls from 136 to 112 and `reverseCsrBytes` from 88 to 64.

The narrowing also shortens the pull's per-node index stream. Visiting a node reads both ends of its row, so that stream is 8 bytes a node instead of 16 — four from the transpose's bounds and four from the projection's own. Counting every array the unweighted pull touches in node order, a node costs 56 bytes instead of 64 at f64 and 48 instead of 56 at f32; the random gathers into the shares array are unchanged, which is why the measured gain is smaller than the halved arc stream would suggest.

**Two ceilings arrive with this, and they are refusals, not fallbacks.** A projection now holds at most `u32::MAX` nodes and at most `u32::MAX` arcs. A graph past either is refused with a named `AlgorithmError::Unsupported` — at the degree count and at the prefix sum that forms the row bounds, on the checked add that would otherwise wrap, rather than in a second pass over the edges.

That ceiling is worth sizing honestly, because "4 billion" sounds close until you price the graph that reaches it. The first graph an eight-byte fallback would admit has 2³² arcs: 17.2 GB of targets at the narrow width, 34.4 GB of original-edge slots beside them, and a 137 GB `ProjectionEdge` list to build it from. At 2³² nodes, the node-id vector's pointers alone are 34.4 GB and one `f64` score array is another 34.4 GB, of which PageRank needs three. The row bounds and the targets are among the smallest arrays in a working set already measured in hundreds of gigabytes, and every per-arc and per-node `usize` buffer in the crate would have to be narrowed before a wide offset array could matter. Louvain's and Leiden's per-level scratch CSR keeps eight-byte offsets: it is a separate structure, off the pull's per-node path, and narrowing it is its own ceiling argument to make another day.

## One pass per iteration

The parallel PageRank pull walked the nodes three times an iteration: a pass forming every source's share and the dangling mass, the pull over in-arcs, and a residual pass over old and new scores. One pass now does all three. Visiting a node, it sums the node's in-arc shares, forms its new score, adds the move to the residual, and forms the node's share for the next iteration — or adds its new score to the next iteration's dangling mass.

That the scores come out bit-identical is not a coincidence to be checked afterwards; it is the reason the fusion is legal. The dangling mass feeds the next `base`, which is the arithmetic the shares pass used to perform over the scores the pull had just written, from the same operands in the same order. The residual and dangling partials are formed per fixed 4,096-node chunk in node order and folded in chunk order, as before, each worker's chunk being a whole number of fixed chunks. `tests/pagerank_fused.rs` checks nine cases — PageRank, ArticleRank, a converging tolerance, a skewed personalization, weighted graphs including one with zero-weight rows and `f64::MAX` weights — at both precisions and at one, two, three and sixteen workers, against a sequential three-pass reference and against digests the previous kernel produced.

Two smaller things ride along. Without a personalization the pull forms `base * (1/n)` once instead of reading a uniform teleport array per node, and releases the array on entry. A weighted pull precomputes each in-arc's probability once before the iterations, so an arc costs one multiply instead of two random reads and two divisions; an arc out of a dangling row is stored as zero, which adds nothing to a sum of nonnegative terms at either precision, so the arc loop no longer branches at all.

Two more passes over the kernel followed. PageRank's per-node share divided by `out_degree + damp`, where `damp` is ArticleRank's mean outgoing weight and is exactly zero on every PageRank path; the two passes are now monomorphised on whether it is zero, and PageRank divides by the out-degree alone, converted to the score type in one step instead of through `f64`. And the non-finite check, which tested every updated score inside the arc loop, now tests once per reduction block on the residual that block has just summed, scanning the block's own scores only when that residual is itself non-finite. Both are bit-identical rather than merely close, and the changelog carries the equivalence argument in both directions — including the one case, two `f64` terms near `f64::MAX`, where a residual test alone would get it wrong, which is why the block scans rather than trusting the residual.

## The default accounting mode got much cheaper

Cooperative budgets are how an untrusted or shared caller can be given an algorithm without being given the machine: work is charged as it is performed, memory is admitted before it is allocated, and cancellation and an optional deadline are observed during execution. The default `counted` mode is the one that enforces all of it, and it was the largest single term measured anywhere in the pull kernel — an ablation attributed 18.7–21.8% of the per-sweep cost to it at 2,097,152 nodes and one thread.

The fused pass charged `1 + in-arcs` per node, one work-meter call per visited node. A block's arc total is one subtraction on the transpose's row bounds, so the pull now makes a single charge of `block_nodes + block_arcs` per 4,096-node reduction block — exactly the sum the block's nodes used to make one at a time.

Three properties are preserved deliberately, because a cheaper meter that quietly weakens a budget is not cheaper:

- **A completed kernel charges the identical total**, so every budget decides exactly as it did. The least budget the pinned 3,000-node pull fits in is 129,002 units before and after.
- **The charge still precedes the work it names**, so no work a budget refused is ever performed. What moves is only *where* a refusal lands — on a block boundary rather than a node boundary — and therefore the units left standing on the counter when a refused run stops. That is the one thing the pinned budget sweep records beyond the outcome, and its digest is re-pinned with the reason written in place.
- **Cancellation and the deadline stay as responsive as they were.** Charging per node reached the meter's admission about once per 1,024 units, so each block loop now polls interruption explicitly on that same cadence — every 113 nodes on an eight-arc graph, every 1,024 on an arcless one — through a new `WorkMeter::poll`, which is the interruption half of `charge` with nothing charged.

Two allocation-level repairs landed alongside. Each work meter's balance is now padded to a whole cache line, so two balances never share one; it had been a bare 32-byte heap chunk sharing a line with whatever the allocator had freed beside it, which since the projection build went parallel was the pool's own bookkeeping, written by other cores. And `WorkMeter::charge` is `#[inline(always)]` again, with the uncounted meter's deadline sample moved out into a cold never-inlined call — the sample's body had outgrown LLVM's inlining threshold and pushed `charge` out of line in sixteen kernels.

## What the measurements say, and where they stop

Timing figures below come from campaign B9 of the companion benchmark, committed with its evidence bundle at `a62e68c` on `work/bench-b9`. It ran PageRank alone, hub and uniform fixtures, at `4a9e7f5` — the head of this release's kernel stack — with `grust` v0.22.0 as the anchor and `neo4j-graph` as the reference participant. Parity ran before anything was timed: 144 PageRank rows all agreeing, f64 rows bit-identical to v0.22.0.

**The boundary comes first, because it decides what the numbers mean.** No two participants stopped at the same iteration count on the same fixture, so the comparison is the cost of one sweep over the arcs, not the time to an answer; the bundle prints both columns and every comparison is drawn on the per-iteration one. The host was restarted between campaigns and the participants whose code did not change moved anyway — over 48 cells of unchanged code the median B9/B7 per-sweep ratio is 0.942, with individual cells from 0.644 to 1.203 — so a B9 millisecond is not a B7 millisecond, and every figure here is formed from two cells of B9.

On the sweep cost, as the results document states it:

> Twelve of the sixteen like-for-like cells put Grust's sweep at or below the reference's; one more is above by less than its margin. Three are above by more than their margin, and all three are at one thread on the protocol-size fixtures: `uniform-16384` by 0.4% ± 0.2, `hub-65536` by 10.8% ± 0.2 and `uniform-65536` by 14.7% ± 0.5. The two at 65,536 nodes are the largest margins in the table and they are not small: a sequential sweep of a graph that fits in L3 costs Grust about an eighth more than it costs the reference here. Nothing in this campaign explains that, and none of the five commits in the stack was aimed at it.

On what the meter costs, the ratio of `counted` to `unchecked` on the same cell of the same run:

> Over the 32 pull-kernel cells the meter's cost in B9 runs from 0.952 to 1.075, and 10 cells differ from 1 by more than the margin on that cell […] On the same cells in B7 it ran from 1.023 to 1.557, with 28 cells outside their margins.

Below 1 is the meter costing less than no meter, which on a memory-bound kernel is what a charge folded out of the inner loop can look like inside dispersion. The push kernel is not in that state: over its 16 cells the meter costs 1.285 to 1.846 in B9 against 1.185 to 1.727 in B7, and on 14 of them the B9 figure exceeds the B7 figure by more than both margins together. The push is sequential by construction and was not a target of this stack.

## Also in this release

**Executions can have children.** `ExecutionContext::child(ChildLimits)` makes an execution that draws memory from its parent's budget but keeps its own work counter, work budget, cancellation and deadline — so an embedder serving concurrent queries can bound the whole process by one budget without every query sharing one cancellation flag and one contended counter. Memory is admitted at every level in one decision; cancellation reaches down, never up; work is not aggregated.

**Work accounting can be turned off by name.** `ExecutionContext::with_accounting(limits, accounting)` takes an `Accounting` with two independent switches — `work` (`Counted` or `Disabled`) and `interruption` (`Observed` or `Disabled`) — with constants for the useful combinations. `ExecutionContext::new` is unchanged and still counts work, and `work_units: usize::MAX` still means "no budget, still counted" rather than an opt-out. A limit the chosen mode cannot enforce is refused at construction rather than accepted and ignored: a finite `work_units` with uncounted work, or a deadline with interruption disabled, is `InvalidArguments`. Memory admission is never disabled in any mode. `ResourceUsage::work_units` is now a `WorkCount`, either `Counted(n)` or `NotCounted` — the release's one breaking type change — because a mode that counted nothing should not report zero as though it had. Kernel results are bit-identical in every mode.

**A cached projection runs its kernels on the querying execution**, not on the one that happened to build it, so a long-lived cache no longer pins a budget or a cancellation flag from a query that has finished.

**Projections build in parallel** when the execution asks for concurrency, and `GraphProjection::prepare_incoming` builds the transpose eagerly for callers who know they will need it.

**Arrow results carry the registered schema, not one read off the rows.** Batches were built with `RecordBatch::try_from_iter`, which marks a column nullable exactly when that batch happens to hold a null — so two batches of one result could disagree, and `bfs` reported `distance` non-nullable on a batch where every node was reachable. Every batch, empty ones included, now carries the kernel's declared nullability, and a batch that contradicts the declaration fails the cursor with `OutputContract`. Integer columns are Int64 as declared.

## What is not here

**No Cypher surface changed**, beyond the `precision` option on two procedures. `grust-cypher`'s language profile is what it was in Mysid.

**No backend was re-qualified.** These kernels run over a projection built from a snapshot, so no backend planner is involved, and no live backend was re-tested for this release.

**The f32 path is PageRank and ArticleRank only.** Every other kernel is f64, and the `Score` trait is sealed rather than open — this is a second precision for two kernels, not a generic numeric layer.

**Two cells on protocol-size fixtures are unexplained.** The 65,536-node one-thread sweeps quoted above cost about an eighth more than the reference's, nothing in the campaign accounts for it, and it is recorded rather than deferred to a later story.

**The narrowing's own timings are shape, not result.** The per-commit measurements in the changelog were taken on a laptop, are labelled as shape only, and several of the individual steps sit at or inside that host's noise floor. The B9 bundle on the dedicated host is the record; the laptop rounds say which direction a change moved and nothing about how much.

## Upgrading

Langoustine is a lockstep release: move every direct Grust crate dependency to 0.23.0 together.

- `PageRank` is now `PageRank<F = f64>`. Existing uses need no change; a signature that names `PageRank` in a position where the default cannot be inferred will need `PageRank<f64>` written out.
- `ResourceUsage::work_units` is a `WorkCount` rather than a `usize`. Code that read it as a number can use `ResourceUsage::counted_work()`, which returns `Option<usize>`, and now has to decide what to do when accounting was off.
- A projection of more than `u32::MAX` nodes or more than `u32::MAX` arcs is refused with `AlgorithmError::Unsupported`. Code matching that error exhaustively sees two new occasions for it, not a new variant.
- `estimateCsr` and `projectionStats` report smaller byte figures for the same graph. A test that pinned the old numbers is pinning the old representation.

Everything else is additive.

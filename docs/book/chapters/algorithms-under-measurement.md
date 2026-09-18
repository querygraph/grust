# Graph algorithms under measurement

This chapter documents what the companion algorithms benchmark measured about
this library, on current sources rather than a frozen snapshot. Everything here
was measured on one host — an 8-vCPU Xeon E5-2686 v4 instance, two CPUs and
4 GiB per service, algorithm concurrency one — and where a number depends on
that host, the chapter says so. Results from three source pins are kept apart
and never pooled.

The benchmark's job is not to rank engines. It runs several execution classes
over identical graphs and states what each timer contains, so a difference can
be attributed to something specific. Twice in this round the attribution
overturned the obvious explanation, which is the reason the chapter exists.

## Execution classes, not engines

Six current columns run the same algorithms through different machinery.

| Column | What its timer contains |
|---|---|
| direct | kernel and result conversion, projection timed separately |
| ordinary Cypher | parse, policy validation, projection, row consumption, with full-path distance verification timed apart |
| Arrow | row-to-Arrow conversion, native Arrow projection, Arrow result consumption |
| DataFusion | complete node and edge scan plans, then the same native kernels |
| Turso direct and Cypher | Grust kernels over a verified snapshot from a durable Turso database |

The Turso columns are not Turso-native SQL graph algorithms, and their database
loading is not an ingestion comparison against another engine's projection. The
Arrow and DataFusion columns do not claim DataFusion executes graph kernels;
DataFusion prepares input, and the kernels that follow are the same ones direct
execution runs.

Because the classes do unequal work by construction, a ratio between two of them
is a statement about machinery, not about speed in the abstract.

## Full paths are an output contract

A shortest-distance query returns one number per destination. A full-path query
returns the intermediate nodes and the accumulated cost along the route. On a
chain, the path to the first node holds one entry, the next holds two, and
across all destinations each array holds `n(n + 1) / 2` entries: 134,225,920 at
16,384 nodes and **2,147,516,416 at 65,536**. Every entry is constructed and
consumed. Nothing is summed in closed form, no family is special-cased, and
paths are reconstructed one at a time into reused buffers rather than retained
together.

That contract is what makes the benchmark informative about this library, since
it exercises reconstruction, the work meter and result conversion at a scale
where each of them is visible.

## The cooperative budget was the kernel's largest cost

Kernels charge the shared budget once per unit of graph work — per visited entry
and per path step — which is what makes an exhausted allowance stop a kernel
where it stands. On the 16,384-node chain the meter is entered about 134 million
times, and profiling attributed **72.8% of kernel self time to `charge_work`**,
against 14.8% for visiting paths and 6.6% for advancing path buffers. The meter
took a mutex on every call, in a single-threaded kernel.

The counter and the cancellation flag are now atomics, with each charge admitted
through a compare-exchange that recomputes admission against the value it
replaces, so budgets are still enforced exactly and granularity is still per
unit. Full-path Dijkstra improved by up to 29.4% on direct execution, except on the
hub family, where it was flat at -2.9% and +1.1%; PageRank improved between
22.5% and 29.1% across every family.

A share of self time is not a share of removable wall time. The atomic still
costs and the surrounding work is real, so a 72.8% profile share produced a 20
to 29% improvement, not a threefold one.

## Deadline enforcement is a policy, and policies differ

Ordinary Cypher's full-path query measured about ninety times direct execution.
The query text was not the cause: removing the row expansion entirely, asking
only for `count(*)` and `sum(size(nodeIds))` rather than one `UNWIND` row per
entry, saved about 4%.

Profiling put roughly 83% of the remainder in the clock. A bounded read policy
requires a finite deadline, the benchmark's Cypher participant disclosed a
24-hour ceiling, and the execution context therefore read the clock on every
charge — about 8.4 million times at 4,096 nodes. Direct execution passes no
deadline, never reads the clock, and completed the same work in 197 ms.

Two facts turn that into a policy difference rather than an engine difference.
The host's clocksource is `xen` rather than `tsc`, so each read goes through a
paravirtual clock instead of a register, which inflates any per-unit check on
this machine specifically. And the compared engine samples its own termination
check: its shipped artifact carries a 10,000-node check interval and a
10,000-millisecond flag interval, so it consults a cached flag between samples.
This library checked every unit. The resulting difference was in how often each
system asks, not in how fast either computes.

Charges now sample the deadline every 1024 units. An interval sweep showed the
gain complete by 256 and flat thereafter, so the interval stays tight and
remains an order of magnitude stricter than the 10,000-unit interval it is
measured against. Cancellation is never sampled, budget limits still fail
exactly at their limit, a memory reservation keeps an exact check while the
per-copied-row memory charges sample as work charges do, and `checkpoint` reads
the clock every time.

The first version of that change tracked its sampling counter even when no
deadline existed, so kernels that set none — every direct, Arrow and DataFusion
path — paid an atomic they had never paid before, and measured 13 to 46% slower
until a paired run caught it. An execution without a deadline now returns before
both the counter and the clock.

## Correctness is an oracle, not an afterthought

Every sample in every sweep is validated against an independent C++ reference,
and failures are retained rather than discarded. That is how a defect unrelated
to performance surfaced.

A durable-loading experiment failed all 36 of its samples. Results were being
associated with nodes by position in the snapshot rather than by node
identifier. Bulk loading and single-writer loading insert in input order, so
position and identifier coincided and the defect was invisible; four concurrent
writers scrambled insertion order, and every distance landed on the wrong node.
The values were an exact permutation of the reference — identical multisets,
wrong positions.

Snapshot verification could not catch it, by construction: it compares sorted
records because database scan order is legitimately arbitrary, which makes it
blind to a permutation. The adapter now restores input order after verification,
in a separately reported phase outside every algorithm timer. No published
measurement was affected, because every published run used bulk loading.

## Allocator and durable loading

The global allocator is a measured default rather than an assumption. A matched
control differing only in six global allocator declarations found mimalloc
faster in 41 of 48 cells, by as much as 27.8% on sparse random graphs, with
three cells slower and reported, led by DataFusion on the chain at +5.4%.

Group commit is a property of durable loading, not of kernels, and is measured
as its own preparation workload. Engine grouping roughly halves durable load
time — 9,962 ms to 4,232 ms at 1,024 nodes — while the algorithm timers do not
move at all. No group-commit setting may be credited as a kernel optimization.
WAL declines the four-writer workload outright with a locked database, which is
why the experiment is specified for MVCC only.

## What the whole set moved

On the 65,536-node chain, across three pins, with the frozen historical binaries
byte-identical throughout and moving by at most 1.4% — the control that makes
the rest attributable to code rather than to the machine:

| Column | baseline | with the meter and deadline work | with the executor work |
|---|---:|---:|---:|
| direct | 66,477 | 52,142 | 51,869 |
| Arrow | 241,622 | 184,957 | 184,291 |
| ordinary Cypher | 5,808,625 | 535,450 | 594,419 |

The full run fell from 3 hours 32 minutes to 35 minutes of wall time. Ordinary
Cypher on that case moved from roughly fifteen times the compared engine's
server query to about 1.55 times it, while remaining a different measurement:
that engine's projection is built before its timer starts and this one's is
inside it.

The reference-executor work that followed improved ordinary Cypher between 88.6%
and 98.1% across every graph family at 4,096 nodes. The full-path chain was the
one case it did not reach: it regressed there by 2.0% at 4,096, 9.8% at 16,384
and 11.0% at 65,536, because that case is dominated by materialising one
heap-allocated string per path entry rather than by the per-row overhead the
work removed.

Reporting that case led to the next change, which stopped deep-copying each
yielded value into every row and began admitting work per path, or per 1024
steps, instead of per entry. Both the regression and the original cost went with
it. On the 16,384-node chain, ordinary Cypher fell from 36,913 ms to 20,255 ms,
direct execution from 3,190 ms to 1,298 ms, and Arrow from 11,612 ms to
9,397 ms, while the frozen C++ participant moved 0.4% in the same runs. At 4,096
nodes with five measured samples, direct execution improved 58.7% and ordinary
Cypher 45.2%. The per-entry charge that the first profile found was therefore
worth roughly a further 2.4x on direct execution once it was charged per path;
the 65,536 case has not been re-run at that pin.

## Limitations

These numbers are not portable. The deadline and clock findings are shaped by a
paravirtual clocksource, and the same code on a host with a register clock would
show a smaller penalty. The 16,384 and 65,536 results are single samples and
establish completion, not stable ranking. Container memory peaks are
whole-container figures including file cache and are never presented as
per-participant resident memory. Results from different source pins are kept in
separate sets. No result from the separate graph-query or strain benchmarks is
combined with these.

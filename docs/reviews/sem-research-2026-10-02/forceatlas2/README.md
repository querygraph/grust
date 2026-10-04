# ForceAtlas2 on Sail: a paper study

Date: 2026-10-02. Sail tree read: `~/src/sail-pecan-integrated`, branch
`work/nutmeg-int64-identity`, commit `4b88c8fb4`. No Sail code was run. The only
thing executed is `estimates.py` in this directory (numpy arithmetic and a
quadtree cell count on synthetic points); its output is `estimates.out`.

Tags used below: **[R]** read from the cited source, **[C]** computed here
(arithmetic shown or in `estimates.py`), **[I]** my inference.

## Summary

1. Yes, it is possible in theory. Everything in ForceAtlas2 except repulsion is one Pregel-shaped join and aggregate, per-row arithmetic, and one global aggregate. Repulsion is a 2D N-body sum and is the only hard part.
2. A Barnes-Hut tree is O(|V|) and does not depend on |E|: about 0.72 internal cells per vertex, 24 B per cell plus 12 B per body, so about 28 MiB, 279 MiB, 2.7 GiB and 27 GiB for |V| = 1e6, 1e7, 1e8, 1e9. That is the size of the position table itself.
3. The proposed architecture does not fit Sail as built. Sail has no broadcast variables, a Python UDF closure travels inside the plan and is capped by a 128 MiB message (about 4.6e6 vertices for a full tree), a native scalar function has no closure at all, and workers keep nothing between jobs.
4. What fits is the inverse: send 12 to 20 B per vertex to one native kernel in the driver process (the shape Nutmeg already has) and keep attraction relational. That is realistic to about 1e7 vertices, and to 1e8 with a large driver. Beyond that it needs Morton-range partitions with per-partition trees (the "locally essential tree" method), which is research-grade work.
5. The larger cost is not the tree. It is hundreds of iterations at one job and one checkpoint each. The smallest experiment is one ForceAtlas2 iteration without repulsion in the existing Pregel loop shape, timed, then repulsion computed outside Sail at |V| = 1e6. It needs no Sail change.

## 1. ForceAtlas2 as an algorithm

Source: Jacomy, Venturini, Heymann, Bastian, "ForceAtlas2, a Continuous Graph
Layout Algorithm for Handy Network Visualization Designed for the Gephi
Software", PLoS ONE 9(6): e98679, 2014,
[doi:10.1371/journal.pone.0098679](https://doi.org/10.1371/journal.pone.0098679).
I read the article XML and the 20 display-formula images. Where the paper is
silent I read the reference implementation it points to (Gephi,
`modules/LayoutPlugin/.../forceAtlas2/` at `master`, fetched 2026-10-02:
`ForceAtlas2.java`, `Region.java`, `ForceFactory.java`, `NodesThread.java`).

### 1.1 Forces

`d` is the Euclidean distance between two nodes, `deg` the degree.

| Force | Formula | Paper | Notes |
| --- | --- | --- | --- |
| Attraction, default | `F_a(n1,n2) = d(n1,n2)` | eq. 1 | Along each edge. No constant. **[R]** |
| Attraction, LinLog mode | `F_a = log(1 + d)` | eq. 3 | The `+1` handles superposed nodes. Tighter clusters, slower convergence. **[R]** |
| Edge weight | `F_a = w(e)^delta * d` | eq. 6 | `delta` is "Edge Weight Influence". 0 ignores weights, 1 is proportional. **[R]** |
| Dissuade hubs | `F_a = d / (deg(n1) + 1)` | eq. 7 | Divides by the degree of the node the edge leaves. Gephi multiplies back by the mean mass to keep the total energy comparable (`ForceAtlas2.java:181-188`, `:219`). **[R]** |
| Repulsion | `F_r(n1,n2) = k_r (deg(n1)+1)(deg(n2)+1) / d` | eq. 2 | Every pair of nodes. `k_r` is the "Scaling" setting. The `+1` keeps isolated nodes repelling. **[R]** |
| Gravity | `F_g(n) = k_g (deg(n)+1)` | eq. 4 | Toward the centre, weighted like repulsion. **[R]** |
| Strong gravity | `F'_g(n) = k_g (deg(n)+1) d(n)` | eq. 5 | `d(n)` is the distance to the centre. **[R]** |
| Prevent overlap | `d' = d - size(n1) - size(n2)`; if `d' > 0` use `d'` in eq. 1 and 2; if `d' < 0` then `F_a = 0` and `F_r = k'_r (deg(n1)+1)(deg(n2)+1)`; if `d' = 0` no force | unnumbered | `k'_r = 100` in Gephi. Local speed is divided by 10. The paper says to apply it only after convergence. **[R]** |

In vector form the repulsion on node `i` from node `j` is
`k_r m_i m_j (p_i - p_j) / |p_i - p_j|^2` with `m = deg + 1`. Gephi computes
exactly this (`ForceFactory.java:143-146`: `factor = coefficient * mass1 * mass2
/ distance / distance`, applied to `xDist, yDist`). **[R]** This is the force of
a logarithmic potential, the 2D gravity or Coulomb kernel, with the degree plus
one as mass. **[I]** So the 2D N-body literature applies unchanged.

### 1.2 Adaptive speed

`F_t(n)` is the total force on `n` at step `t` (attraction plus repulsion plus
gravity). All formulas **[R]**.

| Quantity | Formula | Paper |
| --- | --- | --- |
| Swinging of a node | `swg_t(n) = \|F_t(n) - F_{t-1}(n)\|` | eq. 8 |
| Local speed | `s(n) = k_s s(G) / (1 + s(G) sqrt(swg(n)))`, `k_s = 0.1` in Gephi | eq. 9 |
| Local speed cap | `s(n) < k_smax / \|F(n)\|`, `k_smax = 10` in Gephi | eq. 10 |
| Global swinging | `swg(G) = sum_n (deg(n)+1) swg(n)` | eq. 11 |
| Traction of a node | `tra_t(n) = \|F_t(n) + F_{t-1}(n)\| / 2` | eq. 12 |
| Global traction | `tra(G) = sum_n (deg(n)+1) tra(n)` | eq. 13 |
| Global speed | `s(G) = tau * tra(G) / swg(G)` | eq. 14 |
| Displacement | `D(n) = s(n) F(n)` | text after eq. 8 |

`tau` is the "Tolerance" setting. Gephi defaults: 0.1 under 5,000 nodes, 1 up to
50,000, 10 above. The rise of `s(G)` is limited to 50% per step (the percentage
is an inline image in the article that I did not open; Gephi has
`maxRise = 0.5`, `ForceAtlas2.java:327-328`). **[R]**

The Gephi code is not identical to the paper. It scales the tolerance by an
estimate that depends on the node count, keeps a "speed efficiency" factor that
it multiplies by 0.5, 0.7 or 1.3 depending on the swinging to traction ratio,
and uses `factor = speed / (1 + sqrt(speed * mass * swinging))` for the local
speed (`ForceAtlas2.java:298-328`, `:360-365`). **[R]** A port has to choose
which of the two it reproduces. Other implementations follow the code.

### 1.3 Barnes-Hut in ForceAtlas2

The paper says only that the Barnes-Hut optimisation is implemented, that it
"generates approximation and may be counter-productive on small networks", and
that without it "the complexity time is O(n^2)". Its benchmark setting is
`BarnesHutTheta 1.2`. **[R]** Details are in the code **[R]**:

- The tree is rebuilt from scratch every iteration (`ForceAtlas2.java:176-179`).
- A region holds mass, centre of mass, and `size = 2 * max distance of a member from the centre of mass` (`Region.java:76-98`).
- A region is split into four at its centre of mass, not at the geometric midpoint. If all nodes fall into one quadrant they become single-node regions (`Region.java:101-181`). Leaves hold one node.
- Opening rule: a region is used as one body when `distance * theta > size`, otherwise its sub-regions are visited (`Region.java:183-197`). Default `theta` is 1.2 (`ForceAtlas2.java:546`).
- Positions are stored as `float` (`ForceAtlas2.java:350`).

### 1.4 What one iteration reads and writes per vertex

| Per vertex | Read | Written |
| --- | --- | --- |
| Position `x, y` | yes | yes |
| Mass `deg + 1` | yes | no (static) |
| Force of the previous step `F_{t-1}` | yes | replaced by `F_t` |
| Global speed `s(G)` | yes (one scalar) | updated once per step |

### 1.5 Scope of each part

| Part | Needs | Kind |
| --- | --- | --- |
| Mass | Degree | One aggregate over the edges, once |
| Attraction | The edges and both endpoint positions | Edge-local |
| Repulsion | Every other vertex, or a tree over them | Global, N-body |
| Gravity | Own row (the centre is the origin) | Row-local |
| Swinging, traction | Own row: `F_t`, `F_{t-1}` | Row-local |
| Global speed | A sum over all vertices | One scalar per step |
| Displacement | Own row and the scalar | Row-local |

### 1.6 Iterations

- The paper's benchmark records quality at steps 1, 2, 4, ... up to 2048, on 68 networks of 5 to 23,133 nodes. It states that on the biggest networks "the convergence is slow (more than 1,000 steps)". It also states "ForceAtlas2 is not adapted to networks bigger than 100,000 nodes, unless allowed to work over several hours". **[R]**
- Brinkmann, Rietveld and Takes (GPU ForceAtlas2, section V) time 500 iterations, "typically more than enough for convergence to a readable layout". **[R]**
- RAPIDS cuGraph `force_atlas2` defaults to `max_iter=500` and says "Good short-term quality can be achieved with 50-100 iterations. Above 1000 iterations is discouraged." **[R]**

Planning figure: 100 to 1,000 iterations, 500 as the default. **[I]**

## 2. A relational formulation

### 2.1 Tables

| Table | Columns | Size | Lifetime |
| --- | --- | --- | --- |
| `E` | `src, dst, w` (both directions of each edge) | 2\|E\| rows | Static |
| `S_t` | `id, x, y, fx, fy, fx_prev, fy_prev, mass, wsum` | \|V\| rows | Rewritten every iteration |
| scalars | `s(G)`, speed efficiency, bounding box | a few numbers | In the client, passed as literals |

`wsum` is the static sum of the edge weights of a vertex.

### 2.2 Attraction is a Pregel message step

The project's loop is `pyspark_pecan/pregel.py`. One superstep is: triplets =
sources JOIN edges [JOIN destinations]; one message row per triplet; GROUP BY
the addressed vertex; LEFT JOIN back to the state (`pregel.py:7-10`,
`:179-191`). "The state is the only relation a step writes, so a step is one
job" (`pregel.py:22`). The state is written as Parquet and read back each step
(`pregel.py:192-193`, `staging.py:58-62`), and a vote to halt adds one small
count job (`pregel.py:199`). **[R]**

For the default attraction the force vector on `u` from edge `(u,v)` is
`w (p_v - p_u)`, because `F_a = d` along the unit vector. So

`F_a(u) = sum_v w_uv p_v - p_u * wsum_u`.

The sum needs only the position of the other endpoint. So attraction is one join
of `E` with the positions on `src`, one GROUP BY `dst` producing two sums, and
the join back to the state. That is the `skip_destination_state` shape of the
Pregel loop and the same shape as a PageRank step. **[I]** Dissuade hubs and
edge weights are static per-edge factors and fold into `w`. LinLog needs `d`,
so it needs both endpoints: two joins. **[I]**

Cost per iteration: 2|E| message rows through one join and one aggregate, plus
|V| rows through the state join and the Parquet write.

### 2.3 Gravity, speed and displacement

Gravity, swinging, traction, local speed and displacement are expressions on one
row. The global speed is two sums over `S_t` and becomes a scalar.

There is an ordering constraint. `s(G)` at step `t` depends on `F_t` for all
vertices, and the displacement at step `t` depends on `s(G)`. In one plan that
means the force sub-plan feeds both an aggregate and the per-row update, so it
is computed twice or must be materialised. The cheap arrangement is: **[I]**

1. Job `t` reads `S_{t-1}`, applies the displacement of step `t-1` per row using the scalar as a literal, computes `F_t` at the new positions, and writes `S_t`.
2. A small job computes the two sums over `S_t`. The client updates `s(G)`.

That is one large job and one small aggregate per iteration, the same pattern
as the vote count in `pregel.py:199`.

### 2.4 Repulsion

Repulsion is a sum over all other vertices for every vertex. A plain join is
|V|^2 rows. This is the hard part. Sections 3 to 5 treat it.

## 3. The Barnes-Hut tree as an object

### 3.1 Number of cells

Measured with `estimates.py` part 1: a region quadtree on 1e5 and 1e6 synthetic
points, splitting while a cell holds more than `bucket` points. Three point
sets: uniform, 200 Gaussian clusters with widths over two decades, and a dense
core with a sparse halo (log-normal radius). **[C]**

| Point set, 1e6 points | Bucket | Depth cap (bits) | Internal cells per point | Non-empty leaves per point | Cells per point with 4 child slots | Depth reached |
| --- | --- | --- | --- | --- | --- | --- |
| uniform | 1 | 26 | 0.722 | 1.000 | 2.89 | 19 |
| clustered | 1 | 26 | 0.724 | 1.000 | 2.90 | 26 (cap) |
| core and halo | 1 | 26 | 0.668 | 0.951 | 2.67 | 26 (cap) |
| core and halo | 1 | 16 | 0.032 | 0.057 | 0.13 | 16 (cap) |
| uniform | 16 | 26 | 0.046 | 0.136 | 0.18 | 9 |
| clustered | 16 | 26 | 0.047 | 0.136 | 0.19 | 18 |
| core and halo | 16 | 26 | 0.045 | 0.135 | 0.18 | 26 (cap) |

Reading:

- With one point per leaf, a quadtree has about 0.72 internal cells per point. This matches `1 / ln 4 = 0.721`, the constant for random 4-ary tries (from memory; the simulation is the evidence). The ratio barely moves with the distribution as long as the depth cap is not hit.
- A plain quadtree has no bound on depth: two points at distance `delta` in a box of side `D` need depth `log2(D / delta)`. In the worst case the cell count is O(|V| * depth). A compressed quadtree (chains of single-child cells removed) has at most |V| - 1 internal cells for any input. Gephi's tree has the same bound, because every region it splits ends up with at least two sub-regions (`Region.java:101-181`). **[I]**
- A depth cap trades cells for accuracy. In the core and halo set a 16-bit cap leaves 0.03 internal cells per point because most points share maximum-depth cells. Those cells then need direct pair sums. Realistic layouts are of this kind: dense cores around hubs.
- A bucket of 16 points per leaf cuts the cells by a factor of about 15.

### 3.2 Bytes per cell

| Field | Compact (f32) | Wide (f64) |
| --- | --- | --- |
| Centre of mass `x, y` | 8 B | 16 B |
| Mass | 4 B | 8 B |
| Size | 4 B | 8 B |
| Index of the first child | 4 B (u32, up to 4.29e9 cells) | 8 B |
| Child mask or leaf count | 4 B | 8 B |
| Cell total | 24 B | 48 B |
| Body (`x, y, mass`) | 12 B | 24 B |

The bodies are part of the object. A tree without the points cannot compute the
near field.

### 3.3 Total size

Compact layout, one point per leaf, 0.72 internal cells per point (measured),
and the compressed-tree bound of 1.0. State row for comparison: `id` (8 B) plus
five numbers (`x, y, fx, fy, mass`), 28 B in f32 and 48 B in f64. **[C]**

| \|V\| | Internal cells | Cells only | Cells + bodies | Bound (1.0 cells per point) | Wide (f64) | State table f32 / f64 |
| --- | --- | --- | --- | --- | --- | --- |
| 1e6 | 7.2e5 | 16.5 MiB | 27.9 MiB | 34.3 MiB | 55.8 MiB | 26.7 / 45.8 MiB |
| 1e7 | 7.2e6 | 164.8 MiB | 279.2 MiB | 343.3 MiB | 558.5 MiB | 267 / 458 MiB |
| 1e8 | 7.2e7 | 1.6 GiB | 2.7 GiB | 3.4 GiB | 5.5 GiB | 2.6 / 4.5 GiB |
| 1e9 | 7.2e8 | 16.1 GiB | 27.3 GiB | 33.5 GiB | 54.5 GiB | 26.1 / 44.7 GiB |

With a bucket of 16 the cells shrink to 1.1 MiB, 11.4 MiB, 114 MiB and 1.1 GiB,
and cells plus bodies to 12.6 MiB, 126 MiB, 1.2 GiB and 12.3 GiB.

So the tree is about 29 B per vertex, O(|V|), and about the size of the state
table. It does not depend on |E|. For scale: an edge list with two 8-byte ids is
16 B per edge, 256 B per vertex at |E| = 16|V|. The tree is about 11% of the
edge table. **[C]**

Truncated trees, dense upper bound `(4^(L+1) - 1) / 3` cells of 24 B **[C]**:

| Levels 0..L | Cells | Bytes |
| --- | --- | --- |
| L = 6 | 5,461 | 0.1 MiB |
| L = 8 | 87,381 | 2.0 MiB |
| L = 10 | 1,398,101 | 32.0 MiB |
| L = 11 | 5,592,405 | 128.0 MiB |
| L = 12 | 22,369,621 | 512.0 MiB |

### 3.4 Build and traversal cost

- Build is O(|V| log |V|): sort the points by Morton key, then one linear pass. Barnes and Hut rebuild the tree every time step, and so does Gephi. **[R]** I did not measure a build. A radix sort of 64-bit keys at 50 to 100 million keys per second per core is my assumption, which gives seconds for 1e8.
- Traversal: with a uniform density, the cells of side `s` accepted at one level lie between distance `s/theta` and `2s/theta`, an area of `3 pi s^2 / theta^2`. That is 6.5 cells per level at `theta = 1.2` and 37.7 at `theta = 0.5`. With `log4 |V|` levels: **[C]**

| \|V\| | Levels | Cell interactions per vertex, theta 1.2 | theta 0.5 |
| --- | --- | --- | --- |
| 1e6 | 10.0 | 65 | 376 |
| 1e7 | 11.6 | 76 | 438 |
| 1e8 | 13.3 | 87 | 501 |
| 1e9 | 14.9 | 98 | 564 |

Gephi's `theta` is not the classic ratio, because its region size is twice the
largest member distance from the centre of mass. The table is an order of
magnitude, not a prediction.

A measured reference point: Brinkmann et al. report 9 hours for 500 iterations
on 4 million nodes and 120 million edges with their sequential C++
implementation, against 14 minutes on a GPU. **[R]** That is
`9 * 3600 / 500 / 4e6 = 16 microseconds` per vertex per iteration for all
components on one core. **[C]** Scaled linearly:

| \|V\| | Core-seconds per iteration | 16 cores, ideal | 500 iterations on 16 cores |
| --- | --- | --- | --- |
| 1e6 | 16 | 1 s | 8 min |
| 1e7 | 160 | 10 s | 1.4 h |
| 1e8 | 1,600 | 100 s | 14 h |
| 1e9 | 16,000 | 1,000 s | 5.8 days |

At 1e9 vertices the computation is cluster-sized whatever the framework.

## 4. The proposed architecture against Sail as it is

The proposal: broadcast the tree to the workers, hold it in the closure of a
ScalarUDF, compute repulsion per vertex row on the workers, rebuild the tree on
the driver each iteration from one wide aggregate plus collect.

### 4.1 Does Sail have a broadcast mechanism?

Not a broadcast variable. I found no broadcast-variable code in
`crates/sail-python-udf`, `crates/sail-plan` or `crates/sail-spark-connect/src`
(case-insensitive search for "broadcast"). **[R]**

Sail does have a data-plane broadcast between stages. `InputMode::Broadcast`:
"For each partition in the current stage, execute a single partition to fetch
the input which reads all channels from all partitions in the input stage"
(`crates/sail-execution/src/job_graph/mod.rs:156-159`). **[R]** It is used for:

- the build side of a `CollectLeft` hash join (`job_graph/planner.rs:326-342`); the mode is kept for inner-type joins and rewritten to a partitioned join for Left, LeftAnti, LeftSemi, LeftMark and Full (`planner.rs:156-190`);
- the left side of nested-loop, cross and piecewise-merge joins (`planner.rs:351-371`);
- a scalar subquery: "ScalarSubqueryExec reads the link as a scalar value on every output partition, so the materialized stage is exposed as one broadcast input" (`planner.rs:707-720`).

So in Sail a broadcast is a small relation that every consuming task reads in
full. It is per task. I found no per-worker cache that tasks share. **[I]**

### 4.2 How a Python UDF closure reaches a worker

- The client pickles the function with its closure into the Spark Connect plan. The PySpark client and the Sail server both limit a message to 128 MiB (`pyspark/sql/connect/client/core.py:129-133`; `crates/sail-common/src/config/mod.rs:8`; `crates/sail-spark-connect/src/entrypoint.rs:59`). **[R]**
- The server copies the pickled command into a payload, with the length as an `i32` (`crates/sail-python-udf/src/cereal/pyspark_udf.rs:131-132`). `PySparkUDF` holds that payload as bytes (`crates/sail-python-udf/src/udf/pyspark_udf.rs:35`). **[R]**
- In cluster mode the payload is encoded into the physical plan (`crates/sail-execution/src/proto/codec.rs:3652-3655`), the plan is encoded once per job and stage (`driver/job_scheduler/core.rs:724-732`, cached per scheduling pass in `driver/actor/handler.rs:636`), and it is sent once per batch of tasks, where a batch is one (job, region, stage, worker) (`handler.rs:626-630`, `worker/client.rs:47-67`). The plan is one `bytes definition` field of one unary request (`proto/sail/worker/service.proto:18-22`). The worker service accepts at most 128 MiB (`worker/actor/rpc.rs:56-57`). **[R]**
- On the worker the protobuf is decoded once per batch, but "every task gets a fresh converter, executable plan, and shuffle reader/writer" (`task_runner/actor/handler.rs:61-65`, `task_runner/preparation.rs:86`). Each task builds its own `PySparkUDF` (`codec.rs:3071`) and unpickles the payload lazily on first use (`pyspark_udf.rs:96-99`). **[R]**
- The function is then called once per record batch (`pyspark_udf.rs:135-153`), 8,192 rows by default (`crates/sail-common/src/config/application.yaml:394-396`), under `Python::attach` (`pyspark_udf.rs:140-141`). **[R]** So Python evaluation in one worker process is serialised by the interpreter lock unless the callee releases it. **[I]**

Answer: the closure travels in the plan, once per stage and worker, is unpickled
once per task, and is used once per batch. In `local` mode the plan runs in the
same process and nothing is encoded (`application.yaml:1-9`). **[I]**

### 4.3 The size limit of a plan

128 MiB for one task definition, because it is one gRPC message
(`GRPC_MAX_MESSAGE_LENGTH_DEFAULT`, `config/mod.rs:8`; the internal clients raise
their decode limit to the same value, `crates/sail-execution/src/rpc.rs:113-118`).
The payload is also copied several times on the way (`codec.rs:3655`,
`task/definition.rs:100`, `worker/client.rs:56`). **[R]**

At 29.3 B per vertex a full tree fits one message up to 4.6e6 vertices.
Positions alone (12 B) fit up to 1.1e7. **[C]**

### 4.4 How a native scalar function would hold state

It cannot hold a closure. A native extension scalar is encoded as the pair
(package identity, name) and nothing else
(`crates/sail-common-datafusion/src/native_scalar.rs:93-99`), and is resolved
from a registry in the worker process (`native_scalar.rs:72-91`): "Only
immutable, placement=any scalar implementations enter this process registry"
(`native_scalar.rs:77`). The worker binds the package once per process
(`crates/sail-session/src/extensions/mod.rs:403-409`), and the guide says to
"install identical scalar-plugin wheels on every worker"
(`WRITING-AN-EXTENSION.md:181-182`). **[R]** So state can only arrive as an
argument: a literal (inside the plan, same 128 MiB cap), or a value from the
data plane such as a scalar subquery. I did not verify that a native function
receives a scalar-subquery value as one scalar without per-row expansion.

The three native shapes in the tree **[R]**:

| Shape | Example | Where it runs | State |
| --- | --- | --- | --- |
| Scalar function, `placement: any` | Sedona | Workers, per batch | None. Name only crosses the wire. |
| Driver relation, `placement: driver` | Nutmeg | Driver process, "gathering distributed inputs" (`WRITING-AN-EXTENSION.md:30-31`); "Staged sources have one driver partition" (`nutmeg/README.md:108-109`); kernels "execute in the driver even when the surrounding Sail query uses workers" (`README.md:136`) | A resident graph per session, 256 MiB quota by default (`README.md:10-12`). A driver-only package cannot export scalar functions (`extensions/mod.rs:258-263`). |
| Worker relation, `placement: worker` | Argentea | Workers, per partition | Scoped to one job and closed with it (`task_runner/extension_scope.rs:53-57`). Payload at most 262,144 B, descriptor at most 1 MiB (`worker_extension.rs:24`, `:56`). Inputs can be routed by integer ranges of a column (`:27-33`). One attempt, retry disabled (`:274`, `:318`). |

Workers are also removed after 60 seconds idle by default
(`application.yaml:152-155`). There is no long-lived worker state to update in
place. Every iteration ships or rebuilds whatever the workers need.

### 4.5 What `collect` of |V| rows costs

The tree needs `x, y, mass` per vertex: 12 B in f32, 20 B with an id. The rows
go from the workers through the driver to the Python client as Arrow batches.
The client then has to build the tree in Python or in a native library, and
send it back. The only ways back are the plan (128 MiB) or a file that the next
job reads as a table.

### 4.6 Data movement per iteration

Full tree, one point per leaf, 29.3 B per vertex. "Consumer" is one task,
because the broadcast is per task. Default task slots per worker: 8
(`application.yaml:218-221`). **[C]**

| \|V\| | Collect up (12 B) | Tree down, one consumer | 8 consumers | 64 consumers | Fits one 128 MiB message | Attraction messages at \|E\| = 16\|V\| |
| --- | --- | --- | --- | --- | --- | --- |
| 1e6 | 11.4 MiB | 27.9 MiB | 223 MiB | 1.7 GiB | yes | 488 MiB |
| 1e7 | 114 MiB | 279 MiB | 2.2 GiB | 17.5 GiB | no | 4.8 GiB |
| 1e8 | 1.1 GiB | 2.7 GiB | 21.8 GiB | 174.5 GiB | no | 47.7 GiB |
| 1e9 | 11.2 GiB | 27.3 GiB | 218 GiB | 1,745 GiB | no | 477 GiB |

The attraction column is 2|E| messages of 16 B (an id and two f32). One copy of
the tree is 5.7% of it and the collect is 2.3%. In bytes moved the tree is not
the dominant term. The limits are elsewhere:

- As a closure or a literal it stops at 4.6e6 vertices (the message cap).
- As a broadcast relation there is no message cap, but every task holds its own copy and must turn rows back into a tree. At 1e8 that is 2.7 GiB per task and up to 21.8 GiB per worker with 8 slots. At 1e9 it is not reasonable.
- The collect is tolerable at 1e8 (1.1 GiB per iteration into the client) and not at 1e9.
- The tree build is serial on one machine in every variant.

Direct answers to the three questions:

| Question | Answer |
| --- | --- |
| Can the tree be broadcast efficiently? | Only as a relation read by every task. There is no broadcast variable. Reasonable to about 1e7 vertices. |
| Can it live in a ScalarUDF closure? | In a Python UDF, up to 128 MiB of plan, about 4.6e6 vertices, re-sent every iteration. In a native scalar function, no. |
| Can it be updated on the driver by one aggregate plus collect? | A fixed-level grid can: `GROUP BY cell` yields at most 4^L rows and the driver never sees \|V\| rows. An adaptive tree cannot come out of one aggregate. |

### 4.7 The cheaper variants

**Collect only a coarse tree.** A `GROUP BY (level, cell)` on the workers gives
mass and centre of mass per cell. For levels 0 to 10 that is at most 1.4 million
rows, 32 MiB (section 3.3). It does not need to visit the client at all: it can
stay a relation and enter the next stage as a broadcast join input (section
4.1). If a native scalar function is wanted, the grid can be collected (32 MiB)
and passed as a literal argument, within the plan cap up to L = 11.

**What it loses.** A coarse tree gives the far field only. At 1e8 vertices and
4^10 cells the mean is 95 vertices per cell, and far more in dense regions.
Inside a cell and its neighbours the coarse tree says nothing, and that is where
the 1/d force is largest. Alone this is a particle-mesh method (section 5.3),
not Barnes-Hut. It needs a local complement, which is section 5.5.

**Invert the flow.** Instead of sending 29 B per vertex to every task, send 12
to 20 B per vertex once to one native kernel in the driver process, build the
tree there, compute the repulsion there on all cores, and return `(id, rx, ry)`
as a relation that joins back to the state. No broadcast, no closure, no worker
state. This is the shape Nutmeg already has (section 4.4). The tree never
leaves the process that built it. The cost is that repulsion runs on one
machine. Since the tree is 11% of the edge table and the work is O(|V| log |V|)
with no |E| in it, one machine is the right place for it well past the point
where the edges need a cluster. **[I]** Section 7 builds the draft design on
this.

## 5. Formulations that need no broadcast

Reference for all row counts: the attraction step produces 2|E|/|V| rows per
vertex, 32 at |E| = 16|V| (the Graph500 edge factor).

### 5.1 Relational Barnes-Hut on a multilevel grid

Setup, all plain SQL **[I]**:

- Key: quantise `(x, y)` to `L_max` bits per axis inside the bounding box and interleave the bits (a Morton key). The cell of a vertex at level `l` is `key >> 2(L_max - l)`, an integer expression.
- Level tables: `GROUP BY (level, cell)` giving mass, mass-weighted position sums and a count. Aggregate the finest level from the vertices, then roll each level up from the one below. Each level has at most min(4^l, |V|) rows.
- Leaf level of a vertex: the first level where its cell holds at most `bucket` points.

Far field, three ways:

| Variant | How | Rows per vertex per iteration |
| --- | --- | --- |
| (a) Interaction lists, point to cell | For each level from 2 to the leaf level, join the vertex with the at most 27 cells that are children of its parent's neighbours and not adjacent to its own cell (the fast multipole interaction list), and sum monopole forces | 27 per level |
| (b) Level-synchronous traversal | Start with (vertex, root). Each round, pairs that pass the `theta` test emit a force and the rest join to the children. One join per level | `4 pi / theta^2` per level |
| (c) Cell to cell | Each cell joins its 27 interaction cells and accumulates a local expansion; each vertex then joins its own ancestors | 36 / bucket + one per level |

Near field: join each vertex with the vertices in the 3 x 3 leaf cells around
it. At most `9 * bucket` rows per vertex.

Counts from `estimates.py` part 4 **[C]**:

| \|V\| | (a) far, bucket 16 | Near, bucket 16 (upper bound) | (a) total | Ratio to attraction | (b) theta 1.2 | (b) theta 0.5 | (c) total, bucket 16 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1e6 | 188 | 144 | 332 | 10.4x | 87 | 501 | 153 |
| 1e7 | 233 | 144 | 377 | 11.8x | 101 | 584 | 155 |
| 1e8 | 278 | 144 | 422 | 13.2x | 116 | 668 | 157 |
| 1e9 | 323 | 144 | 467 | 14.6x | 130 | 751 | 158 |

Notes:

- In (a) every accepted cell is at least one cell away, so cell side over distance is at most 0.67. That is tighter than Gephi's default `theta` of 1.2. **[C]**
- (b) reproduces the Gephi rule with its own `theta`, but needs 10 to 15 joins in one job, and the near field on top.
- (c) is the true fast multipole structure. With a zeroth-order local expansion it is inaccurate for the nearest interaction cells; with first order and above it is the 2D complex-multipole algebra of Greengard and Rokhlin, expressible as arithmetic on pairs of doubles but intricate. In (c) the near field dominates.
- The measured mean occupancy of a non-empty leaf at bucket 16 is 1 / 0.136 = 7.4 points, so the near field averages about 66 rows per vertex, not 144. **[C]**
- Adaptive leaves break the simple 3 x 3 rule: a sparse cell next to a dense one must not pair with all its points. Adaptive fast multipole codes handle this with four list types. In SQL this is more joins.
- Skew is the real risk. A layout has dense cores. A depth cap that leaves 1e5 points in one cell makes the near-field join quadratic there.

Verdict for 5.1: possible with no native code and no broadcast, still one job
per iteration. But repulsion becomes 3 to 15 times the attraction step in rows:
at 1e9 vertices, 1e11 to 5e11 join rows per iteration. A native traversal does
the same work without materialising a row per interaction.

### 5.2 What a fixed interaction list buys

Nothing is collected and nothing is broadcast beyond small cell tables, which
are ordinary join inputs. The scheme is deterministic and needs no client
round trip except the bounding box (four numbers, which can ride on the speed
aggregate; the displacement per step is bounded by `k_smax = 10`, eq. 10, so
the previous box padded by 10 is safe). **[I]**

### 5.3 Grid only (particle-mesh)

Deposit mass on a G x G grid with one `GROUP BY`, compute the field on the grid
in the driver (G = 2048 is 4.2 million cells, a trivial FFT or direct sum),
and give each vertex the force of its cell by a join or by a native function
with the grid as a literal (two f32 per cell: 32 MiB at G = 2048). One row per
vertex per iteration.

Effect on quality **[I]**: the force is smoothed below the cell size. Vertices
in one cell do not repel each other, so structure inside a cell collapses.
ForceAtlas2's repulsion by degree exists to shape the near field (the paper's
stated aim is to bring poorly connected nodes close to well connected ones
without clutter), and "prevent overlap" is purely near field. Grid-only loses
both. FIt-SNE and t-FDP succeed with interpolation on grids, but their kernels
are bounded at zero distance; ForceAtlas2's 1/d is singular there. A grid needs
a near-field correction (particle-particle particle-mesh, or TreePM as in
GADGET-2).

### 5.4 Random vertex sampling

Gove's method updates a sliding window of n^(3/4) vertices per iteration, each
against n^(1/4) random vertices plus a constant-size neighbour list. **[R]**
(author's summary; the paper's abstract confirms sampling both ways.)

Relationally the sample is a small broadcast relation. At n = 1e8 an iteration
is 1e6 vertices times 100 samples, 1e8 join rows, one row per vertex. But only
1% of the vertices move per iteration. In an engine that pays a job and a
checkpoint per iteration that trade is bad. **[I]** Quality: the author reports
layouts "about the same quality as Barnes-Hut", "sometimes ... a little more
chaotic", and suggests finishing with a few Barnes-Hut iterations. **[R]**

### 5.5 Morton-range partitions with local trees

This is what the N-body community does (section 6): partition the points by
ranges of a space-filling-curve key, build a tree per partition, and give each
partition the part of the other partitions' trees it needs.

In Sail terms **[I]**:

- The domain decomposition is `repartitionByRange` on the Morton key. Range output distribution exists (`crates/sail-execution/src/task/definition.rs:74-77`), and a worker relation can route its input by integer ranges of a column (`worker_extension.rs:27-33`).
- Split points come from the cell histogram of the coarse `GROUP BY`, chosen by the client. They are a tiny literal.
- Stage 1, per partition: build the local tree; emit, for every other partition, the cells that partition could need given its bounding box ("locally essential" cells, coarse far away and fine near the boundary); pass the partition's own points through.
- Shuffle the exports by destination partition.
- Stage 2, per partition: local points plus imported cells; traverse; emit `(id, rx, ry)`.

Everything is rebuilt each iteration, so it needs no state across jobs. It needs
a native operator that sees a whole partition, twice. Sail has two candidates:
a Python `mapInArrow` function over a compiled wheel
(`crates/sail-python-udf/src/udf/pyspark_map_iter_udf.rs`), or the experimental
worker relation. Push-style export fits a dataflow engine. The hashed oct-tree
variant, where a processor asks others for cells on demand during traversal,
does not: Sail has no request-reply path between tasks.

### 5.6 Negative sampling

LargeVis samples M negative partners per positive edge (M = 5 by default) from a
distribution proportional to `degree^0.75`, and optimises by asynchronous
stochastic gradient descent. **[R]** DRGraph and SNAP-tFDP use the same idea.

Relational shape **[I]**: a synthetic edge table with M random partners per
vertex, regenerated each iteration, processed exactly like attraction with the
repulsion expression. M rows per vertex: 5/32 of the attraction rows at M = 5.
It needs a way to draw partners (dense ids make that a random integer; see the
sibling `dense-ids` study). To estimate ForceAtlas2's sum, draw partner `j` with
probability proportional to `deg(j) + 1` and scale by total mass over M.

Effect on quality **[I]**: the estimate is unbiased but noisy, and the 1/d
kernel has a heavy tail, so the near field is poorly sampled. ForceAtlas2's
speed control reads force changes between steps as swinging (eq. 8) and lowers
the global speed (eq. 14), so sampling noise would stall it. The sampling
methods use a decaying step instead. The result is ForceAtlas2's energy model
with a different optimiser. The paper's convergence and quality claims do not
carry over; cluster-level structure probably does.

### 5.7 Multilevel coarsening

Coarsen the graph, lay out the coarsest graph, then place and refine level by
level (FM3, Hu, Multi-GiLA, DRGraph, OpenOrd). It is independent of how
repulsion is computed. It cuts the number of iterations at full size, which is
the expensive resource here. Coarsening by rounds of merging is itself
Pregel-shaped (Multi-GiLA does it in Giraph). The coarsest level can be laid out
exactly by a native kernel. ForceAtlas2 as published is single-level and
"continuous"; multilevel changes the starting point of the last phase, not the
forces, so the final refinement still relaxes toward a ForceAtlas2 equilibrium.
**[I]**

### 5.8 Comparison

| Formulation | Rows per vertex per iteration | Native code | Broadcast | Layout claims of the paper |
| --- | --- | --- | --- | --- |
| Attraction (reference) | 32 | none | none | n/a |
| Relational Barnes-Hut (5.1) | 90 to 470 | none | small cell tables | Kept. Accuracy equal or better than `theta` 1.2 |
| Grid only (5.3) | 1 | optional | grid | Near field lost: no degree-shaped neighbourhoods, no overlap prevention |
| Random vertex sampling (5.4) | about 1, 1% of vertices move | none | sample | Different algorithm; author reports similar metrics |
| Negative sampling (5.6) | M (5) | none | none | Different optimiser; adaptive speed unusable |
| Morton partitions, local trees (5.5) | 1 in, 1 out, plus exports | per-partition operator | bounding boxes | Kept |
| Driver kernel (4.7) | 1 in, 1 out | driver relation | none | Kept |
| Multilevel (5.7) | orthogonal | optional | none | Forces kept; fewer iterations |

## 6. Literature

Each entry was checked on the web on 2026-10-02 for title, authors, year and
venue. "Read" says how much of the content I saw.

### 6.1 Distributed and parallel Barnes-Hut

| Work | Trick | Transfers to a relational engine? | Read |
| --- | --- | --- | --- |
| Barnes, Hut. "A hierarchical O(N log N) force-calculation algorithm". Nature 324:446-449, 1986. [doi:10.1038/324446a0](https://doi.org/10.1038/324446a0) | Tree of cells, each used as one body when far enough. Rebuilt every step. | The tree itself is a set of `GROUP BY (level, cell)` aggregates. | Abstract |
| Salmon. "Parallel hierarchical N-body methods". PhD thesis, Caltech, 1991. <https://thesis.library.caltech.edu/6291/> | Orthogonal recursive bisection of space, and a "locally essential tree": each processor receives the subset of the others' trees its own particles can touch. | Yes. It is push-style: exports keyed by destination, one shuffle. Section 5.5. | Metadata only; the server refused the connection. Technique confirmed from [CS267 lecture notes](https://people.eecs.berkeley.edu/~demmel/cs267-1995/lecture27/lecture27.html) found by search |
| Warren, Salmon. "A parallel hashed oct-tree N-body algorithm". Supercomputing '93, pp. 12-21. [doi:10.1145/169627.169640](https://doi.org/10.1145/169627.169640) | Cells named by a key, found through a hash table. From memory, not re-read: particles sorted along the key order give the domain decomposition, and remote cells are fetched on demand. | Half. The key is a Morton key and the cell table is a keyed relation, which is section 5.1. The on-demand fetch does not transfer. | Search summary |
| Springel. "The cosmological simulation code GADGET-2". MNRAS 364(4):1105-1134, 2005. [arXiv:astro-ph/0505010](https://arxiv.org/abs/astro-ph/0505010) | Domain decomposition along a space-filling curve; TreePM: long-range force on a grid with Fourier methods, short-range by the tree. | Yes. Range partitioning by key, and the grid is one `GROUP BY`. TreePM is the principled form of "coarse grid plus local trees". | Abstract |
| Greengard, Rokhlin. "A fast algorithm for particle simulations". J. Comput. Phys. 73(2):325-348, 1987. [doi:10.1016/0021-9991(87)90140-9](https://doi.org/10.1016/0021-9991(87)90140-9) | Multipole and local expansions with fixed interaction lists, O(N), for the 2D logarithmic kernel, which is ForceAtlas2's repulsion. | Yes. Interaction lists are joins on integer cell offsets. Section 5.1 (a) and (c). | Abstract |
| Burtscher, Pingali. "An efficient CUDA implementation of the tree-based Barnes Hut n-body algorithm". GPU Computing Gems Emerald Edition, pp. 75-92, 2011. | Tree as flat arrays, bodies sorted in tree order, iterative traversal. | The flat-array layout is the model for section 3.2. Not relational. | Not opened. No URL verified. Cited and used by Brinkmann et al. |

### 6.2 ForceAtlas2 at scale

| Work | Trick | Transfers? | Read |
| --- | --- | --- | --- |
| Brinkmann, Rietveld, Takes. "Exploiting GPUs for fast force-directed visualization of large-scale networks". ICPP 2017, pp. 382-391. [doi:10.1109/ICPP.2017.47](https://doi.org/10.1109/ICPP.2017.47), [PDF](https://liacs.leidenuniv.nl/~takesfw/pdf/network-visualization-gpu-icpp2018.pdf) | ForceAtlas2 as GPU kernels: edge-parallel attraction, Burtscher and Pingali's Barnes-Hut in 2D, reductions for the global speed. 40x to 123x over sequential CPU; 4 million nodes and 120 million edges in 14 minutes for 500 iterations. | The decomposition into kernels is the same as section 1.5. It shows one device handles millions of nodes. | Full text |
| RAPIDS cuGraph `force_atlas2`. <https://docs.nvidia.com/cugraph/latest/api_docs/api/cugraph/cugraph.force_atlas2/> | GPU ForceAtlas2 with Barnes-Hut, `barnes_hut_theta` default 0.5, `max_iter` default 500. | A baseline to compare against, not a design. | API page |
| Moradi, Mondal. "BigGraphVis: Leveraging Streaming Algorithms and GPU Acceleration for Visualizing Big Graphs". [arXiv:2108.00529](https://arxiv.org/abs/2108.00529), 2021 | Streaming community detection, then ForceAtlas2 on the community graph. 3 million nodes and 34 million edges in about five minutes. | Yes: coarsen relationally, lay out the small graph natively. | Abstract |

I searched for ForceAtlas2 on Spark, GraphX, Giraph and Flink and found no
paper. I recall grid-cell layouters in the Gradoop (Flink) code base but could
not confirm them by search, so they are not cited.

### 6.3 Distributed force-directed layout on dataflow and vertex-centric systems

| Work | Trick | Transfers? | Read |
| --- | --- | --- | --- |
| Hinge, Auber. "Distributed Graph Layout with Spark". IV 2015, pp. 271-276. [HAL hal-01187421](https://hal.science/hal-01187421) | Force-directed layout on Spark and GraphX, with repulsion computed in MapReduce style. | It is the same engine family. Arleo et al. report it needed 5 hours for 8,000 vertices and 35,000 edges on 16 machines, which is the warning. | Not read (access denied). Figures as cited by Arleo et al. |
| Hinge, Richer, Auber. "MuGDAD: Multilevel graph drawing algorithm in a distributed architecture". 2017. [HAL hal-01516889](https://hal.science/hal-01516889) | Multilevel on Spark: coarsen by maximal independent sets, propagate positions down by a distributed join. | Yes, it is the multilevel wrapper of section 5.7 in relational form. | Search summary only |
| Arleo, Didimo, Liotta, Montecchiani. "A Distributed Force-Directed Algorithm on Giraph: Design and Experiments". [arXiv:1606.02162](https://arxiv.org/abs/1606.02162), 2016. Journal version: "Large graph visualizations using a distributed computing platform", Information Sciences 381:124-141, 2017, [doi:10.1016/j.ins.2016.11.012](https://doi.org/10.1016/j.ins.2016.11.012) | Repulsion only from the k-hop neighbourhood, gathered by controlled flooding. About one million edges in under 8 minutes. | Yes: k rounds of the attraction join. But it drops the global repulsion, so it is not ForceAtlas2's model, and k-hop sets explode on hubs. | arXiv text |
| Same authors. "A Distributed Multilevel Force-directed Algorithm" (Multi-GiLA). GD 2016, [doi:10.1007/978-3-319-50106-2_1](https://doi.org/10.1007/978-3-319-50106-2_1), [arXiv:1608.08522](https://arxiv.org/abs/1608.08522); IEEE TPDS 30(4):754-765, 2019 | Distributed "solar merger" coarsening after FM3, then the k-neighbourhood layout per level with k from 6 down to 1. Ten million edges in about 60 minutes. | Coarsening and placement are Pregel-shaped message rounds: yes. | arXiv text |
| Mueller, Gregor, Lumsdaine. "Distributed force-directed graph layout and visualization". EGPGV 2006. [ACM](https://dl.acm.org/doi/10.5555/2386124.2386138) | Vertices split across processors. | Historical. | As cited by Arleo et al. |

### 6.4 Multilevel and fast single-machine layouts

| Work | Trick | Transfers? | Read |
| --- | --- | --- | --- |
| Hachul, Jünger. "Drawing Large Graphs with a Potential-Field-Based Multilevel Algorithm" (FM3). GD 2004, LNCS 3383, pp. 285-295. [doi:10.1007/978-3-540-31843-9_29](https://doi.org/10.1007/978-3-540-31843-9_29) | Multilevel plus multipole evaluation of the repulsive potential. | Both halves, see 5.1 and 5.7. | Abstract |
| Hu. "Efficient and High Quality Force-Directed Graph Drawing". The Mathematica Journal 10:37-71, 2005. Implemented as Graphviz [sfdp](https://graphviz.org/docs/layouts/sfdp/) | Multilevel plus Barnes-Hut, adaptive step. ForceAtlas2 cites it for its speed control. | As 5.7. | Search summary; journal URL not checked |
| Yunis, Yokota, Ahmadia. "Scalable Force Directed Graph Layout Algorithms Using Fast Multipole Methods". ISPDC 2012. [doi:10.1109/ISPDC.2012.32](https://doi.org/10.1109/ISPDC.2012.32) | Graph layout repulsion through a parallel fast multipole library. | Confirms the kernel is a standard N-body one. | Abstract |
| Martin, Brown, Klavans, Boyack. "OpenOrd: an open-source toolbox for large graph layout". Proc. SPIE 7868, 2011. [doi:10.1117/12.871402](https://doi.org/10.1117/12.871402) | Edge cutting, multilevel, and a parallel implementation. | Multilevel: yes. | Abstract |
| Rahman, Sujon, Azad. "BatchLayout: A Batch-Parallel Force-Directed Graph Layout Algorithm in Shared Memory". [arXiv:2002.08233](https://arxiv.org/abs/2002.08233), 2020 | Update vertices in minibatches against frozen positions. | A Sail iteration is already one synchronous batch. | Abstract |

### 6.5 Layout by sampling and by interpolation

| Work | Trick | Transfers? | Read |
| --- | --- | --- | --- |
| Tang, Liu, Zhang, Mei. "Visualizing Large-scale and High-dimensional Data" (LargeVis). WWW 2016. [doi:10.1145/2872427.2883041](https://doi.org/10.1145/2872427.2883041), [arXiv:1602.00370](https://arxiv.org/abs/1602.00370) | Negative sampling (5 per edge, noise proportional to degree^0.75), asynchronous SGD, linear time. | Yes, as a synthetic edge table. Section 5.6. | arXiv text |
| Gove. "A Random Sampling O(n) Force-calculation Algorithm for Graph Layouts". Computer Graphics Forum 38(3):739-751, 2019. [doi:10.1111/cgf.13724](https://doi.org/10.1111/cgf.13724) | Update a random subset of vertices against a random subset of repulsors. | Yes, but few vertices move per job. Section 5.4. | Abstract and the [author's summary](https://twosixtech.com/blog/graph-layout-by-random-vertex-sampling/) |
| Zhu, Chen, Hu, Hou, Liu, Zhang. "DRGraph: An Efficient Graph Layout Algorithm for Large-scale Graphs by Dimensionality Reduction". IEEE TVCG 27(2):1666-1676, 2021. [arXiv:2008.07799](https://arxiv.org/abs/2008.07799) | Sparse distance matrix, negative sampling, multilevel. Linear time and memory. | Yes, 5.6 plus 5.7. | Abstract and introduction |
| Chen, Hou, Wang, Xue, Feng, Deussen, Huang, Wang. "SNAP-tFDP: Massively Scalable Graph Layouts via Sparse Negative Sampling". [arXiv:2608.01907](https://arxiv.org/abs/2608.01907), 2026 (IEEE VIS 2026 per the arXiv record) | Edge-centric negative sampling that reconstructs a degree-weighted objective in O(\|E\|); 4 million nodes and 34 million edges in under 10 seconds on a GPU. | Yes. It is the closest published support for 5.6 with degree weights. | Abstract only |
| Zhong, Xue, Zhang, Zhang, Ban, Deussen, Wang. "Force-Directed Graph Layouts Revisited: A New Force Based on the T-Distribution". IEEE TVCG, 2023. [arXiv:2303.03964](https://arxiv.org/abs/2303.03964) | A bounded short-range force evaluated with the fast Fourier transform. | The grid half: yes (5.3). The force is not ForceAtlas2's. | Abstract |
| Linderman, Rachh, Hoskins, Steinerberger, Kluger. "Fast interpolation-based t-SNE for improved visualization of single-cell RNA-seq data". Nature Methods 16:243-245, 2019. [doi:10.1038/s41592-018-0308-4](https://doi.org/10.1038/s41592-018-0308-4) | Repulsion interpolated on a grid and convolved with the fast Fourier transform. | As 5.3. | Metadata |
| van der Maaten. "Accelerating t-SNE using Tree-Based Algorithms". JMLR 15(93):3221-3245, 2014. <https://jmlr.org/papers/v15/vandermaaten14a.html> | Barnes-Hut and dual-tree approximations of an embedding gradient. | Same tree, same sizes. | Abstract |

## 7. Verdict and a draft design

### 7.1 Verdict

| Formulation | Jobs per iteration | State on workers | Native code | Reasonable \|V\| | Fit to Sail's model |
| --- | --- | --- | --- | --- | --- |
| Full tree in a Python UDF closure (as proposed) | 2 (collect, apply) | re-sent each time | none | up to 4.6e6 (hard cap) | Poor |
| Full tree as a broadcast relation, per-task rebuild | 1 or 2 | per task | per-partition operator | up to about 1e7 | Poor: every task holds the whole tree |
| Coarse grid only | 1 | none | none | any | Good fit, wrong near field |
| Relational attraction, driver-native repulsion | 1 large, 1 small | none | one driver relation | 1e7 comfortably, 1e8 with a large driver | Good |
| Relational Barnes-Hut | 1 large, 1 small | none | none | any, at 3 to 15 times the attraction cost | Fits, expensive |
| Negative sampling | 1 large, 1 small | none | none | any | Best fit; not ForceAtlas2 |
| Morton partitions with local trees | 1 large, 1 small | job-scoped | per-partition operator | 1e8 to 1e9 | Fits in principle; the most work |

By size **[I]**:

- Up to about 1e6 vertices: do not distribute. The paper's own bound for the Java implementation is 100,000 nodes; a native or GPU implementation handles millions (Brinkmann et al.).
- 1e6 to 1e7, and to 1e8 with a large driver: realistic with relational attraction and a driver-native repulsion kernel. It fits one job per iteration, the state as a checkpointed table, and no worker state. The driver holds about 5 to 6 GiB at 1e8 (positions, tree, output).
- 1e8 to 1e9: repulsion must run on the workers. The method exists (section 5.5) and needs no long-lived state, but it needs a per-partition native operator and a tree-export step. By section 3.4 the compute alone is days on 16 cores at 1e9, so this is a cluster job in any framework. It is fair to ask first what a 1e9-point layout is for: no display shows it without aggregation, and a coarsened graph laid out natively (BigGraphVis, section 5.7) may answer the actual question.
- The iteration count is the binding cost at every size. 500 iterations are 500 jobs and 500 rewrites of the state table (3.7 to 6.7 GiB each at 1e8 with the columns of section 7.2). A multilevel start is the obvious lever.

### 7.2 Draft design: relational attraction, driver-native repulsion

**Tables.**

| Table | Columns | Written |
| --- | --- | --- |
| `E2` | `src, dst, w` with both directions and the static factors folded into `w` (weight power, dissuade hubs) | Once |
| `S_t` | `id, x, y, fx, fy, fx_prev, fy_prev, mass, wsum` | Every iteration (checkpoint) |
| Run scalars | global speed, speed efficiency, iteration, bounding box | Client, and a small record per iteration for restart |

**One iteration.**

1. Positions. Read `S_{t-1}`. Per row, compute the local speed from the literal global speed and the row's two forces, and move the vertex (eq. 9, 10). Plain expressions.
2. Attraction. Join `E2` with the positions on `src`; emit `(dst, w x, w y)`; `GROUP BY dst`; then `F_a = (sum_x - wsum x, sum_y - wsum y)`. One join, one aggregate, 2|E| rows. Plain DataFrame operations, the Pregel message shape.
3. Repulsion. A driver relation takes `(id, x, y, mass)`, builds the tree (Morton sort, flat arrays, bucket leaves), traverses it on all cores with ForceAtlas2's opening rule, and returns `(id, rx, ry)`. This is the only native code.
4. Gravity. Per row.
5. Combine. Join attraction and repulsion to the positions by `id`, sum the forces, shift the old force to `fx_prev, fy_prev`, write `S_t`.
6. Speed. One small aggregate over `S_t`: the two weighted sums of eq. 11 and 13, and the bounding box. The client applies eq. 14 with the 50% rise limit and passes the result to the next iteration as a literal.

**What is native and what is not.**

| Step | Kind |
| --- | --- |
| 1, 2, 4, 5, 6 | SQL or DataFrame operations |
| 3 | One native driver relation, in the Nutmeg package or beside it |
| Loop, checkpoints, cancellation | The existing staging run, as in `pregel.py` |

**Checkpointed.** `S_t` every iteration, the previous one removed, as the Pregel
loop does. The run scalars with it. The tree is never stored.

**Expected cost per iteration.**

| Item | Rows | Bytes |
| --- | --- | --- |
| Attraction join and aggregate | 2\|E\| | 16 B per message |
| Gather to the driver | \|V\| | 20 B per row |
| Repulsion output | \|V\| | 16 B per row |
| Two joins on `id`, one Parquet write | \|V\| each | 40 to 72 B per state row (an id and eight numbers, f32 or f64) |
| Speed aggregate | \|V\| in, 1 out | |
| Native compute | about 16 microseconds per vertex on one core for everything in the sequential reference of Brinkmann et al.; repulsion is a part of that | |

**Extensions, in order of value.**

1. Multilevel start: coarsen relationally, lay out the coarsest graph entirely inside the native kernel, refine downward with tens of iterations per level.
2. Negative sampling as a no-native fallback for sizes where the driver kernel does not fit, accepted as a different optimiser.
3. Morton-range partitions with local trees (section 5.5), replacing step 3 only. Steps 1, 2, 4, 5 and 6 do not change.

**Open risks.**

1. Per-job overhead times hundreds of iterations. The fixed cost of one job of this shape is not known here.
2. Composition. Nutmeg's existing verbs are `stage` (consumes inputs, returns a receipt) and `run` (input-free relation). Whether a driver relation that consumes a distributed input and returns a large relation composes inside one larger plan was not checked. The fallback is two verbs, which costs one more job per iteration.
3. Driver memory. The Nutmeg session quota defaults to 256 MiB and is prepaid. 1e8 vertices need several GiB.
4. Which ForceAtlas2. The paper and the Gephi code differ in the speed control (section 1.2). Results cannot be compared coordinate by coordinate: the paper says the result "varies depending on the initial state". Acceptance has to use a quality measure, for example the normalised edge length the paper uses, against a reference implementation on the same graph.
5. Skew. Hubs have mass up to their degree, cores are dense, and f32 positions may not resolve them. Leaf buckets and a high depth cap matter.
6. Non-determinism. Sum order in distributed aggregates varies, and the layout dynamics amplify small differences.
7. Checkpoint volume: the whole state table is rewritten every iteration.

**The smallest experiment that confirms or kills it.** No Sail change and no
native code.

1. Take one graph of about 1e6 vertices that the project already stages.
2. Write one ForceAtlas2 iteration without repulsion (steps 1, 2, 4, 5, 6) in the shape of the existing Pregel loop. Time it. It should cost about one PageRank step on the same graph, because the join shape is the same. Call it `T`.
3. Kill criterion: if `500 * T` is already beyond the time budget with no repulsion at all, the engine's per-iteration cost decides the question, and only a multilevel variant with few full-size iterations or an all-native kernel remains.
4. If it survives, add repulsion outside Sail: collect `(id, x, y, mass)` to the client (20 MB at 1e6), compute Barnes-Hut repulsion with any existing library, write the result as a table, join it. Run 100 iterations. Compare the paper's quality measure and the picture against a reference ForceAtlas2 (Gephi or cuGraph) on the same graph.
5. Only if both hold, build the driver relation and repeat at 1e7.

## Limits

- Nothing was run on Sail. Every statement about Sail is from reading code at commit `4b88c8fb4`, not from observing behaviour. In particular I did not verify: that no per-worker cache shares a broadcast input between tasks; how a scalar-subquery value reaches a native scalar function; whether a driver relation with inputs composes inside a larger distributed plan; how `collect` batches results to the client.
- No timing in this report is measured. The per-vertex cost comes from one published sequential figure. Tree-build speed is an assumption.
- The interaction counts use a uniform-density model and the classic opening ratio. Gephi's region size and split rule differ, and real layouts are far from uniform.
- The cell counts are from synthetic point sets of 1e5 and 1e6 points, not from real layouts.
- The paper's inline formula images were not all opened. The value 50% for the speed rise limit is from the Gephi source, as are `theta` 1.2 and the tree rules. The Gephi source was read at `master` on 2026-10-02, not at a tagged release.
- Literature not read in full, as marked in section 6: Hinge and Auber 2015 (access denied; its figures are as cited by Arleo et al.), MuGDAD (search summary), Salmon's thesis (server unreachable; technique confirmed from lecture notes), Warren and Salmon 1993 (search summary), Burtscher and Pingali 2011 (not opened, no URL verified), Hu 2005 (journal URL not checked), Gove 2019 (abstract and author's summary, not the paper), SNAP-tFDP, t-FDP, FIt-SNE, GADGET-2, FM3, OpenOrd, the ExaFMM paper, BigGraphVis (abstracts or metadata).
- I found no published ForceAtlas2 on Spark, GraphX, Giraph or Flink. That is a search result, not proof of absence.
- The 1/ln 4 constant is quoted from memory; the simulation supports it.
- The statements about quality under grid-only, sampling and multilevel variants are inferences from the force model. None was tested.

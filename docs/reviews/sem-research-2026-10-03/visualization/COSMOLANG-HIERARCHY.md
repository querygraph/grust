# Cosmolang hierarchy and anticipation

Companion to the [wire protocol](COSMOLANG.md). All policies below are proposed
work. The [original study](README.md) qualifies only its recorded backend
prototypes; it does not qualify this service at multibillion-node scale.

## 1. Hierarchy is a graph quotient, not a large node list

Keep canonical graph tables in storage. Publish a separate immutable hierarchy
with one root or a small root forest, disjoint child memberships and versioned
bounds. A leaf identifies a partition of source vertices. Internal nodes cover
the union of their children, with exact mass/counts and declared summary metrics.
An object has exactly one leaf owner in a hierarchy version. Overlapping
community assignments remain separate analytics; they are not silently used as
a partition tree.

Two hierarchies are useful and must be named explicitly:

- **Spatial:** Morton/quadtree cells for a 2D layout; octree or other 3D bounds
  for genuine 3D coordinates. This controls spatial level of detail and pruning.
- **Semantic:** stable disjoint group/community partitions, optionally WCC at
  an outer level and communities or spatial partitions inside a component.
  Each published hierarchy states algorithm/version/seed and ownership policy.

They can share a leaf-to-vertex membership table, but do not pretend arbitrary
community groups have a single contiguous Morton range. Crosswalks between
hierarchies are materialized relations, not implicit index equivalence.
Hierarchy versions are pinned for a session; a rebuilt hierarchy is a new view
context, with an explicit migration of focus/selection by canonical membership.

| Artifact        | Fields and role                                                                                                                                |
| --------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `HIERARCHY`     | hierarchy/node/parent IDs, level, child-page handles, bounds, exact member mass, summary validity, overflow; no member arrays in a node record |
| `MEMBERSHIP`    | snapshot, hierarchy version, leaf ID, vertex ID; ownership relation and indexed range/page handles                                             |
| `AGG_EDGES`     | snapshot/projection/hierarchy/cut policy, source group, destination group, original edge count, weight summaries, direction and loop policy    |
| `LAYOUT`        | hierarchy/layout versions, node/vertex ID, 2D/3D coordinates, transform, provider/seed, anchor provenance                                      |
| `METRICS`       | graph projection and algorithm contract, scope, vertex/component/group ID, value and exactness                                                 |
| `VIEW_MANIFEST` | frontier/selection, represented mass, point/link counts, omitted-edge information, versions, actual bytes and resource digests                 |

Hierarchy metadata is paged. A memory-capped head cannot contain all nodes of a
skewed hierarchy. Use bounded fanout, compressed unary paths, maximum depth and
explicit overflow pages. A heavy leaf is refined or paged; it cannot bypass the
browser budget because a density estimate was wrong.

## 2. The displayed cut

A **cut** is a disjoint antichain of hierarchy nodes: no member is also the
ancestor of another displayed member. Each original vertex in the requested
domain is represented at most once. Expanding a parent replaces it with its
children; collapsing reverses that operation. If a requested expansion would
exceed budget, coarsen another unpinned region, page the children, retain a
labelled remainder aggregate, or refuse. Do not silently drop unseen members.
Pinned real vertices consume budget; their IDs cannot also be counted inside a
rendered aggregate. A focus exception uses a disjoint remainder aggregate.

For domain `S` and cut owner map `f`, each original edge `(u,v)` whose endpoints
are in `S` maps to `(f(u),f(v))`. Counts/weights come from source edges under the
pinned multigraph/direction policy. Internal aggregate edges are explicit
self-loops or separate internal-edge summaries. Exact aggregate blocks are
computed before top-k display truncation. A quotient can preserve counts
exactly while hiding individual topology; its manifest says `representation:
quotient`, not `full original graph`.

A mixed-depth cut changes incident links beyond the expanded group. Recompute
those links from suitable aggregate blocks or exact endpoint mapping. Do not
assign an ancestor’s edge count to an arbitrary child, sum previously truncated
children, or join both full and refined aggregates into duplicate mass.
A boundary aggregate names excluded membership and direction; it is not an
ordinary source vertex.

Filtering changes membership **before** constructing the cut and edge quotient.
Existing unfiltered cell counts and edges cannot be reused as exact filtered
counts. Reuse only a matching precomputed facet, otherwise compute a new
materialization, schedule it, or label the output approximate/unknown when the
caller explicitly permits that policy. WCC is computed on the pinned source
projection/selection; spatial quotient WCC is a different, labelled computation.

## 3. A billion-node graph within a million-point ceiling

The protocol caps resident drawable points at **1,000,000**. This is an
application ceiling requested by Alexy, not a measured universal Cosmograph
capacity. Negotiate a lower device-specific point/edge/byte budget. Start with
the previous proposal’s 10,000-point overview and 50,000-point detailed target,
then qualify larger views. Aggregate points, boundary points, focused raw
vertices, old/new replacement overlap and decoded prefetched views all count.

For a three-billion-vertex snapshot, an illustrative overview of 10,000 groups
represents 300,000 vertices per group on average. That average does not guarantee
bounded child size or balanced groups. Paged adaptive refinement keeps dense
regions coarse while expanding the user’s focus. A current 100,000-point view
and a 150,000-point replacement occupy 250,000 resident points before release;
encoded disk/network buffers still have separate byte caps.

Node count does not bound edge count. A graph quotient of even 10,000 groups
can contain almost 100 million directed group pairs. Use precomputed bounded
edge summaries, explicit edge admission and disclosed top-k omission; rendering
one million points is not permission to send all their incident edges.
At one million points, five million links, and 2D `idx/x/y` plus
`src_idx/dst_idx/display_weight` numeric columns, the raw numeric portion alone
is **72,000,000 bytes**. IDs, offsets, labels, validity, SDK copies, GPU buffers,
old/new overlap and optional Z add more. Meter those boundaries separately.

The billion-node claim is architectural reach through a quotient, not evidence
that this host can compute every global algorithm or global layout interactively.
Source scans, hierarchy/WCC construction and coarse-edge aggregation may require
a distributed/offline build. Interactive workers serve published bounded
artifacts; Nutmeg stages only projections that its actual memory admission fits.

## 4. Layout precomputation

Compute a coarse hierarchy layout offline. Seed child layouts around parent
anchors and preserve the global transform for stable zoom. The layout manifest
names anchors and the provider/seed. A local relaxed layout is a separate
coordinate version and never redefines spatial ownership behind the client.

When the user hovers an aggregate, prefetch child summaries and suitable incident
edge blocks. If those artifacts fit and background capacity is available,
prepare the next child view/layout. For an admitted neighborhood, reuse resident
CSR across WCC/other approved algorithms and layout providers where the current
Nutmeg API permits. A new layout-provider binding is needed; existing Nutmeg
integration does not itself implement a hierarchical layout service. Full
ForceAtlas2, 3D force layouts and ANN indexes are not supplied by this proposal.
An initial provider can use already materialized coordinates; parent-anchored
local relaxation is a later qualified provider.

Fixed server coordinates and browser GPU simulation are different modes. The
browser can relax a bounded ephemeral view locally; its buffers and coordinates
have their own lease. Switching back restores the named server layout. Pinned
selection/focus survive by source IDs, never draw indices.

## 5. Prediction without changing user intent

Start with deterministic heuristics, not a learned behavior model:

| Observed intent                  | Candidates to prepare                                                             |
| -------------------------------- | --------------------------------------------------------------------------------- |
| Zoom/pan velocity or 3D orbit    | Swept viewport/frustum cells, next finer cut, nearby boundary blocks              |
| Hover/dwell on a group           | Its child summaries, one bounded child view and parent return path                |
| Focus a vertex or follow an edge | Highest-priority outgoing/incoming adjacency pages, bounded one-hop view          |
| Change degree threshold          | Adjacent declared histogram bins or indexed facet views; no speculative full scan |
| Request nearest neighbors        | Next page/rank expansion and relevant index pages for the same model/filter       |
| Open a component                 | Component summary and likely child cut, not a second global WCC run               |
| Back/collapse navigation         | Previous cut and encoded view objects already in the session history              |

Candidates are **complete Cosmolang requests** with the same pinned context and
budgets as foreground work. Their cache key includes snapshot, projection,
selection/predicates, hierarchy/cut, layout/provider/seed, direction, algorithm
contract, ANN settings, requested columns, quality policy and authorization
scope. Shared immutable work uses single-flight execution and reference-counted
leases. Promotion to foreground reuses the exact matching job/artifact; a
nearby-but-different predicate or ANN contract is not an exact cache hit.

Choose at most a small beam (initially two candidates per session). A simple
score is expected saved latency minus compute cost and weighted network/memory
cost; convert each term to declared policy units before comparing it. Record
predicted probability, estimated cost, provenance and later hit/miss. Apply a
short TTL, hysteresis and cancellation on changed snapshots/selections. Fast
motion cancels fine refinement and prepares coarse visible coverage instead.
Prediction events contain no authority to install a view, move the camera,
change filters or expand a selection. A subsequent explicit command is needed.

Keep speculative resources separate and capped: proposed initial per-session
encoded prefetch cap 16 MiB; zero prefetched GPU views; one layout job; two total
candidates; background worker allowance independent of interactive workers.
These are tunable starting policies, not measured capacities. Foreground work
wins admission. Uncancellable kernels run only in a separate bounded worker
pool, so cancellation support is not falsely advertised as hard preemption.
Never prefetch a full global WCC/ANN/layout build because the user might click.

Track encoded cache, decoded server buffers, CSR+maps+scratch, browser Arrow/WASM,
GPU buffers and replacement overlap separately. Current estimates/observations
are not a universal RSS cap; the service must implement real reservations,
stream/output caps and process containment before making that claim.

## 6. Buildable sequence and acceptance

| Stage                         | What we can build                                                                                             | Acceptance evidence                                                                                                                                                               |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| C0: wire contract             | Versioned JSON schemas, error/job/view states, golden exchanges and mock replay                               | This revision: portable schema/example checks; not a live service                                                                                                                 |
| C1: bounded gateway + browser | Typed Sail membership/filter/follow requests; two Arrow objects; fixed 2D Cosmograph adapter; view leases     | Independent source membership/edge oracle; negative and >2^53 IDs; no dangling links; stale/retry/cancel replay; browser install acknowledgement                                  |
| C2: hierarchy                 | Paged Morton cut, quotient edges, expand/collapse; disjoint focus exception                                   | Original mass/edge conservation; mixed levels, disconnected spatial neighbors, skew/hubs, filtered facets; million-point resident cap including replacement                       |
| C3: analytics + MCP           | Degree/WCC artifact adapters, admitted Nutmeg route, spatial/vector nearest adapter; MCP tools/resource links | Same answers and error scope through browser and MCP; source versus display distinction; exact nearest oracle and labelled ANN; observed refusal/cancellation/release             |
| C4: anticipation/layouts      | Two-candidate heuristics, encoded object cache, warmed admitted projections and layout-provider interface     | Replay with prefetch on/off; foreground latency, wasted bytes/CPU, hit rate, no intent mutation or scope leak; latest-intent installation                                         |
| C5: 3D and larger scale       | Qualified SDK camera binding, 3D bounds/frustum serving, offline semantic hierarchy/global artifacts          | Real 3D pose round-trip; deterministic hierarchy publication; trace real pruned bytes; separately measure target device memory/frame latency and billion-source operational costs |

C0 is a reviewable contract. C1 can start without the Grust redesign; C3’s
Nutmeg adapter follows current capabilities and later accepts a v2 provider.
No stage is a promise of p95 latency before measuring network, workers and
browser hardware. Run measurements natively with optimized binaries; use Linux
VMs only for functional/build qualification, per the user’s host policy.

Outstanding decisions: pinned Cosmograph package/API for complete 3D camera
control; first vector-index provider and embeddings; hierarchy stability under
new snapshots; distributed global WCC/layout route; and measured deployment
budgets. None blocks publishing this protocol proposal or a small C1 prototype.

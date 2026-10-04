# Sem's research tasks of 2026-10-02: where each answer is

Five studies, one folder each; the two questions about Grust share one.
None of them built a product feature: they are
studies, counts, plan analyses and small timings, as asked. The short report
on the previous day's questions is
[`../../SEM-REPORT-2026-10-02.md`](../../SEM-REPORT-2026-10-02.md).

| Task | Answer in one line | Folder |
|---|---|---|
| Delta with liquid clustering or Z-order; does the read path carry sort order and co-partitioning; range partitioning | Sail refuses `CLUSTER BY` and `ZORDER`, and the Delta scan declares nothing. `repartition(T, key).checkpoint()` does carry co-partitioning (a round is 15% shorter on graph500-24). A checkpoint after a sort returns wrong results. `repartitionByRange` is hash. | [`delta-order-plans/`](delta-order-plans/README.md) |
| ForceAtlas2 by relational operations; the weight of a Barnes-Hut tree; broadcast and a ScalarUDF closure | The tree is about 29 bytes a vertex and independent of the edges. Sail has no broadcast variable and a closure is capped at 128 MiB. Relational attraction with a driver-side native repulsion kernel fits, to about 10M vertices. | [`forceatlas2/`](forceatlas2/README.md) |
| Attacking the first WCC round with a per-partition union-find | The union-find's output is an edge list, so there is no remapping, no conflict and no reverse mapping. graph500-24, 10 partitions: 260M edges become 38M in a 3.9 s pass. Merging the forests is the whole answer when the vertices fit one process. | [`wcc-first-round/`](wcc-first-round/README.md) |
| Why `OnceLock<HashMap<NodeId, usize>>`; why this model for Grust; a dense alternative after GraphAr | The map only serves source lookups and two sorted Arrow columns would be better. The model is a property-graph API's, inherited by the algorithms. graph500-24 holds 4.99 GB for a 1.08 GB CSR. The kernels already run on a dense CSR; what surrounds them is what a dense model replaces. | [`grust-model/`](grust-model/README.md) |
| Dense ids: an analogue of `zipWithIndex` on Sail; GraphAr's id layout | GraphAr's internal id is the row number within a vertex type; the 16 + 48 bit split is not in its specification or code. `row_number() over (order by id)` gives an exact, ordered, repeatable index today with client code only (0.2 s for 3.8M ids, 3.1 s for 50M). The two-pass `zipWithIndex` is unsafe in local mode, and an id from `monotonically_increasing_id` must be written before it is used. Recommended: do the index, the two joins and the sort in the engine with client code, and measure Banda on dense sorted input before building anything in Sail. | [`dense-ids/`](dense-ids/README.md) |

## Found on the way, and reported upstream

The plan study turned up defects in Sail itself. They were written up as ten
standalone reports and filed, at the user's instruction, as `lakehq/sail`
issues #2722 to #2731:
[`../sail-upstream-reports-2026-10-02/`](../sail-upstream-reports-2026-10-02/README.md).
The first is the one that matters most here: a `checkpoint()` taken after a
sort returns wrong results (#2722).

## How the work was done

- The WCC note and the Grust model report were written directly, with a
  counting program and one profile run to ground them.
- The Delta, ForceAtlas2 and dense-id studies were each done by a separate
  agent from a written brief, then checked: their code citations were read
  against the source, and the Delta study's two central claims were
  reproduced with scripts written apart from its harness.
- Timings are from one laptop (Apple M1 Max) with other work running. They
  show the size of an effect. They are not results to quote.

## What these studies point to, together

Three of them meet at one design, which is Sem's:

1. Dense ids are assigned by the engine (the dense-id study).
2. The engine keeps a declared layout between steps. Today that is
   co-partitioning through a checkpoint, and not sort order (the plan
   study).
3. The kernels take a plain CSR and return dense arrays, with no identity
   type (the Grust model report). The same kernels serve a driver-side
   repulsion step (the ForceAtlas2 study) and a merge of per-partition
   forests (the WCC note).

What has to be true for it to work, and is not yet: Sail must remember a
sort across a write, which is issue #2722 and its neighbours.

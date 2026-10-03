# Sem's two parallel tasks of 2026-10-03: where each answer is

Sem's pull request #35 added two drafts. Each has a design response here.
Neither built product code; each has one small measurement where a number
decided something.

| Sem's draft | Response | The answer in brief |
|---|---|---|
| [`grust-model/PROPOSED_DESIGN_DRAFT.md`](../sem-research-2026-10-02/grust-model/PROPOSED_DESIGN_DRAFT.md) | [`grust-design/`](grust-design/README.md) | Grust becomes an LPG schema, a GQL compiler, CSR kernels and an `io` module, and knows nothing about Sail. The engine should make ids dense but not sort: on graph500-24 Sail maps both endpoints in 5.5 s, and a local counting build from unsorted dense pairs takes 1.2 s holding 1.16 GiB, against 8.0 GiB for in-process mapping and 12.7 GB for Banda today. Sorting in Sail first costs 18 to 25 s at an 11 to 13 GiB peak. Seven open decisions. |
| [`forceatlas2/VIZUALIZATION_SERVICE_DRAFT_FOR_LLM_ANALYSIS.md`](../sem-research-2026-10-02/forceatlas2/VIZUALIZATION_SERVICE_DRAFT_FOR_LLM_ANALYSIS.md) | [`visualization/`](visualization/README.md) | The quadtree becomes three Parquet tables sorted by Morton key; an "expand" is one key-range read, 3 to 43 ms on cit-Patents and graph500-24, about 40 times faster than on unsorted tables. The tree's head fits in memory at any scale (about 33 MiB at 1e9 vertices). Pseudo-edges are precomputed only for coarse levels and computed on demand below. Twelve open decisions. |

Both responses are written by AI agents. The visualization study was done
by a separate agent from a brief and then checked: its new Sail finding was
reproduced independently.

## Found on the way

A sort before a Parquet write is dropped when the write uses
`mode("overwrite")`. Reproduced on unmodified upstream and written up as
standalone report 12, **not filed**:
[`../sail-upstream-reports-2026-10-02/12-overwrite-write-drops-sort/`](../sail-upstream-reports-2026-10-02/12-overwrite-write-drops-sort/README.md).
It matters to both designs: both rely on sorted or clustered Parquet, so
their writers must use the default save mode or a fresh path until it is
fixed.

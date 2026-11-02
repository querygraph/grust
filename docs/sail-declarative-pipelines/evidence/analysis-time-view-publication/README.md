# Analysis-time view publication

Three sequential human-reviewable Sail units:

- `31dfb2cc9d60275ed632e000f153051bd7407e10` on5717: resolve_view_publication
  returns a NamedPlan and existing CreateViewOptions from one native resolution.
  Native CreateView shares the private implementation and retains its input
  through command construction. Three tests compare explicit/inferred native
  metadata and count errors, with no publication or physical planning.
  Exact fmt/strict Clippy/86 Plan+139 Connect libraries pass (225).
- `f4a6a541f5ad5b6bba08f9b60702032257fbf74c` on31df: prepare_catalog_command
  shares the ordinary authority/optimizer/rewrite/physical/rename/diagnostic tail
  with normal resolution. No public node constructor, new owner or stream pump.
  Tests use real Sail planner/local runner/memory catalog: preparation does not
  publish, consumption preserves metadata; CurrentDatabase results/diagnostics
  equal the ordinary path. Exact fmt/strict Clippy/86+141 pass (227).
- `f0ac099e66d811f97dcc668f1c39366948b7cdf3` onf4a6: AnalyzedGraph exports
  only SchemaRef and CreateViewOptions maps, with no LogicalPlan field. Full plans
  stay in the working set until analysis ends; all mock provider leases drop
  before return. Persisted-view metadata comes from its analysis resolution.
  Publication uses those options through the prepared catalog path and same
  runner drain; replace=true/if_not_exists=false preserved. Materialize-tables
  order, dry runs and view publication outside refresh selection retained.
  Exact fmt/strict Clippy/86+143 pass (229).

The artifact tests deliberately evolve954's historical shape: temporary providers
no longer survive the exported result. A Tail helper over a temporary mock source
requires the full working plan during analysis (one memory scan) before export.
A publication test removes the source after analysis and publishes captured SQL,
columns/types/nullability/comments/namespace through the real planner/runner/catalog
with no scan or second resolution. The clock test checks ordinary Sail resolution
remains unfolded before schema-only export. Arrow schema/field metadata remains;
separate DataFusion qualifiers/functional dependencies are not an exported identity.

Negative control `373cd270d1b282be37315436dcf205095a4465f8` adds only a second
resolution before publication. Six unchanged artifact tests give5pass/1fail:
source-unavailable publication fails. Other five pass. No initial positive-source
gate failures in these three units. No new scheduling mechanism/stress verdict.

Fresh combined CLI onf0ac passes300 selected public+67 upstream Python executions,
client/server Spark4.2.1, rebuilt binary/source/identities pinned, server exit0/no
remaining listener. The frozen reusable harness is under the existing
[public harness](../local-runner-ownership/public-harness/README.md); replay with
full commit and a fresh output directory. This is not original Scala-suite
acceptance. No captured execution ownership, per-command re-resolution/config
fusion, SDK, ORC writer, cluster or durable streaming/CDC activation.

Fable9954f812 source review and coordinator CF-0241 precision response are archived.
Generic invalid input/ToDf/incompatible-view errors already failed in analysis
before this refactor; do not attribute all pre-write failures to it. The new
observable guarantee is no second view/source resolution after successful analysis.
Existing views.feature's private-view failure checks both output and otherwise
valid table are not published. Original source and gates/controls are preserved.
SHA256.json covers packet files except itself; historical absolute paths identify
advancement-time evidence, not a promise that temporary outputs stay on disk.

Use fable-review-updated.md (Grust0e16b01f / CF-0242) for current wording;
it incorporates both coordinator precision notes while retaining the original
9954f812 snapshot separately. No source change requested by the review.

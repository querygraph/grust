# Batch provider migration source audit

Pinned Sail17b8ac254 and Spark6176183960 excerpts distinguish graph analysis,
persisted-view publication and execution's own provider-plan cache. Every excerpt
has full commit/blob/source-file SHA256 and line coordinates in source-pins.json.
These are source observations, not live provider, original Scala test or effect
verdicts. The active design is BATCH-PROVIDER-MIGRATION-DESIGN.md two levels up.

Sail exports full temporary-view analysis plans but only schemas for other outputs,
including persisted views. Its CreateViewOptions stores SQL and column/namespace
metadata, not the resolved query input; execution uses a fresh plan map. The
cross-command provider cache is in execution's own temporary/read_output plans.
Do not claim analysis-time Delta providers are physically scanned from the
analysis map on this batch path. The retained Delta store-lineage hazard remains
for any plan actually reused across future owners.

Spark BatchTableWrite reanalyzes the requested flow's upstream closure while
stopping at materialized boundaries. Its persisted-view publication uses an
already analyzed logical plan and creation namespace. Reference FlowAnalysis
fuses upstream flow SQLConf; this needs precedence/config tests during migration.
No new runtime behavior is selected by source excerpts. See separate artifact
characterization evidence when its exact gates are qualified.

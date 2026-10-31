# Dynamic identifiers and Connect references in SDP

Status: active design checkpoint, announced to the user before starting. The first
implementation unit is general literal-identifier normalization. Computed-identifier
policy and Connect-reference expansion/registration lifetime are not yet activated.
No opaque provider slot, cached relation overload, session mutation or streaming
permission is selected here. Preserve Sail's pure definitions, schema/publication
exports and per-command fresh provider maps.

## Evidence that constrains the design

Spark4.2.1 AstBuilder.withIdentClause immediately turns a non-null string Literal
into a named logical relation using parseMultipartIdentifier. Other expressions
remain PlanWithUnresolvedIdentifier, even when constant-foldable. FlowAnalysis
substitutes CTEs and traverses UnresolvedRelation before Dataset.ofRows performs
ordinary semantic analysis. ResolveIdentifierClause materializes computed names
later. Treating a string literal and CONCAT as equivalent early graph reads changes
behavior.

The initial nine public Spark observations demonstrate this distinction:

- IDENTIFIER('z_sensitive') reads the local graph view and inherits its settings.
  With true settings, selecting Foo from its foo output fails unresolved-column
  analysis. A materialized table producer is also a graph input for this form.
- IDENTIFIER(concat('z_', 'sensitive')) does not find that temporary graph view in
  the catalog. It fails TABLE_OR_VIEW_NOT_FOUND instead of inheriting its config.
- A literal external read succeeds with an unrelated configured graph view.
  Adjacent static true-view reads still affect its semantic column resolution.
- The literal CTE reference works. Further computed-name/CTE/sampling observations
  are retained in the expanded oracle; use the packet rather than inference.

The six-case public protobuf WithRelations oracle establishes a separate split:

- A used scalar plan-ID reference contributes graph-view settings, including when
  nested under a function. With conflicting outer-view settings, the two probes
  reach DUPLICATE_FLOW_SQL_CONF after successful semantic analysis.
- Unused references, including an unused SubqueryAlias in the generic form, do
  not contribute settings. Both controls return value2.
- SQL root + nonempty all-SubqueryAlias references triggers Spark Connect's
  SQLWithRefs path. Each reference is analyzed and temporarily registered during
  transformation, then root SQL is executed and temporary views removed.
  A local graph-view parameter fails TABLE_OR_VIEW_NOT_FOUND at registration;
  an external-table parameter registers and subsequently returns Foo9.

The seventh lifetime witness replaces that external catalog entry after flow
registration, keeping the original external files intact. The current catalog
returns bar10, while the pipeline still returns Foo9. This rules out treating SQL
parameter registration as validation followed by fresh name resolution on every
run. The input binding is observably frozen across catalog replacement.

Spark generic transformWithRelations builds a plan-ID map and substitutes
UnresolvedPlanId expression nodes. SQLWithRefs is selected from the original
protocol form before SQL is lowered. A structural references-first traversal is
not equivalent to either path. Source comments require acyclic references; exact
missing-ID, duplicate-ID and nested-reference behavior still needs qualification.

## First review unit: literal normalization

Normalize only spec::Expr::Literal(Utf8(Some(name))) in the SQL analyzer, through
Sail's existing object-name parser, into ReadType::NamedTable. Leave computed,
cast, null and parameter forms as DynamicTable. Preserve aliases and samples.
The grammar's missing IDENTIFIER TABLESAMPLE field is supplied with the same
TableSampleClause parser used for ordinary tables; both read variants retain it.
Original SQL remains in persisted definitions. Do not evaluate helpers in parsing.

This makes the existing ordered trace see exactly the statically named relation,
without extending that trace with a second expression evaluator. Direct AST
comparisons with ordinary table syntax test multipart names, quoted dots, aliases
and samples. Invalid literal names fail during parsing; computed/null forms remain
late. The runtime test's name is updated because a literal SQL identifier is now
intentionally a named relation, not a witness for the computed dynamic path.

## Next review units and boundaries

1. Qualify computed external reads, computed CTE names and expression reads before
   selecting their native resolver policy. The computed target must not be treated
   as an early graph read merely because constant folding produces a local name.
   An expression's actual subqueries remain visible inputs; they are not the same
   as its eventual computed target. Preserve the private setting and helper phase.
2. Prefer a narrowly defined RelationScope policy seam over global catalog/session
   mutation: ordinary callers keep current behavior; SDP's late computed target
   can use native CTE/catalog resolution without recording a graph dependency.
   The exact seam is pending the expanded reference and native witnesses. Do not
   turn arbitrary valid expressions into bounded-streaming admission refusals.
3. Retain the SQL-parameter versus generic-reference distinction at the Connect
   boundary. Today SQL is parsed away before spec::WithRelations, so its source
   form cannot reliably be reconstructed from a Project node. A pure mode/tag or
   frontend normalization may be needed; no representation is selected yet.
4. For generic references, use lexical plan-ID lookup and expand only actual
   occurrences, preserving expression traversal order, plan IDs and canonical
   attribute identity. Add a typed plan-reference visitor instead of silently
   skipping nested Expr::Subquery IDs. Preserve repeated uses and local shadowing;
   detect malformed/cyclic references with native-compatible diagnostics.
5. SQL parameters require registration-time validation under ordinary session
   rules, outside graph lookup. That alone does not prove correct later binding.
   The provider/schema lifetime witness establishes that fresh name resolution
   changes the observed source across catalog replacement. An explicit immutable
   source description or owned binding contract is required before this path can
   be claimed compatible. Do not retain
   LogicalPlan/providers in sail-common or quietly reintroduce analyzed graph
   provider exports to imitate Spark. If an immutable source descriptor or owned
   binding capability is required, review it with the existing ownership design.
6. Prove each unit using the original public protocol, then Rust native witnesses,
   unchanged controls and a fresh combined CLI. Do not represent helper tests as
   upstream Scala execution or close broad binding parity from rows alone.

## Remaining design work

The raw protocol, source pins, initial/expanded observations and failures are in
[evidence/dynamic-binding-design](evidence/dynamic-binding-design/README.md).
Registration versus analysis versus execution errors remain separate observations.
The provider-freezing representation/lifetime, generic reference cycles/duplicates,
computed-name helper errors, scope/config changes between calls, native CTE policies and command closure
changes remain unfinished. Captured preparation/admission, session shutdown,
streaming/Iggy/CDC durability and full original Scala acceptance remain separate
required work. The goal is active; this document does not select an easier target.

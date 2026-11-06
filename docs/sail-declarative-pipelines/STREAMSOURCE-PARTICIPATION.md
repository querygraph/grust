# Preserve streaming sources when no rows pass

A continuous computation must retain its sources even when a filter emits no data.
Checkpoints, watermarks and source failures still need an execution path. Lower
streaming relations into Sail's flow-event operators after analysis and before
ordinary logical optimization can remove them.

This increment establishes an execution-planning boundary. It does not establish
durable source identity, distributed checkpoint alignment or successful durable
completion when a consumer cancels.

## Zero data does not mean zero participation

Sail carries user data and ordered control markers through the same stream. A
filter such as `WHERE FALSE` removes every data row but must retain markers and
source failures. Replacing that computation with a bounded empty relation discards
the source, its position and any path for a later checkpoint.

The reference implementation currently asks DataFusion to analyze and optimize
before detecting streaming table providers. DataFusion 55.2's filter and limit
elimination rules can remove the entire source first. Earlier detection alone
would retain a Boolean classification while still losing the executable scan.

Sail already has source wrappers, data-only filter and projection nodes, stream
limits and a collector that exposes bounded results. Protect the actual operators
before pruning, rather than constructing a second execution graph for sources
that disappeared from the data plan.

## Use a mandatory compiler boundary

Sail already separates configured name/type analysis from logical optimization.
Insert shared mandatory preparation between them in the execution and explain
compiler paths. Expose the complete Sail compilation helper for programmatic
callers. Bare DataFusion APIs remain DataFusion entry points; they do not implement
Sail's streaming compiler.

Keep analysis exactly once. Pass the actual session's optimizer context into
preparation, preserving its query timestamp, registry and configuration. Ordinary
batch input passes through unchanged. Already lowered streaming graphs remain
unchanged when compilation runs again.

Before lowering admitted unary/union/source graphs, retain existing data-only scan
pushdowns with an explicitly audited subset: Sail's expression simplification,
DataFusion filter pushdown, projection optimization, then common-expression
sharing. Apply their declared
traversals directly, for at most three rounds, stopping when unchanged. Never
invoke the full optional optimizer here. Unsupported source-bearing relational
shapes skip these preparation rewrites and reach their named streaming refusal;
this prevents global-aggregate pruning from erasing a source. Bounded expression
subqueries retain ordinary batch treatment.

The preparation subset preserves source scans while normalizing limit/offset
expressions and pushed predicates. Verify actual requested columns, filters and
materialized bytes using a counting source, including exact and inexact pushdown.
An opaque source wrapper must not cause wide scans to read unused payload columns.
Re-audit the subset when its dependency implementation changes. Repeated immutable
functions must retain their existing work sharing. A counting-function probe
produced identical data but exposed duplicated evaluation after early lowering:

| Four data rows, one immutable expression selected three times | Function calls | Evaluated rows |
| --- | ---: | ---: |
| Existing late lowering | 1 | 4 |
| Early lowering without common-expression sharing | 3 | 12 |

Run the public common-expression rule after projection merging, before the
flow-event nodes hide their expression trees. Verify immutable sharing, volatile
calls and conditional evaluation with counters and exact results. Marker ordering
must not change, and conditional expressions must not evaluate previously unused
branches.

Only after preparation lower into the existing flow-event nodes and run the
configured ordinary optimizer. A first optimizer rule would be skippable under
`max_passes=0` or `skip_failed_rules=true`. An analyzer rule lacks the real query
timestamp required for existing constant folding. The explicit compiler boundary
avoids both weaknesses without inventing global state or refusing those settings.

Keep DataFusion's established explain/error behavior through a narrowly attributed
owned compilation routine if its orchestration must change. Preserve qualified
payload fields and metadata when the collector restores the public data schema.
Links and retained comparison against the pinned implementation support ownership.

Discover sources through supported aliases, renamed providers, exposed view plans
and expression subqueries. Bounded scalar subqueries must preserve their existing
batch and physical preparation. A stream hidden inside an expression subquery
must receive a named refusal before pruning unless its execution topology is
explicitly supported. Verify currently working queries before widening refusals.
Known raw view-provider forms that cannot expose an admitted flow graph must fail
explicitly; opaque providers must declare their source protocol.

Commands execute once through their existing ownership path. Tail counting,
inferred pivot values, crosstab values and time-travel scalar bounds collect during
resolution, before final compilation. Refuse declared streaming inputs there before
eager evaluation; keep bounded inputs unchanged. Apply the same refusal to raw
stream-bearing memory-table creation and prepared-statement commands forwarded by
Sail's command wrapper. Do not add unrelated SQL command support merely to claim
coverage of direct DataFusion APIs.

## Preserve occurrence identity

Two reads of one source can be distinct participants. The logical source wrapper
currently compares schema and scan options while ignoring source identity.
Once wrappers enter optimization, that equality can falsely identify different
occurrences as the same node.

Allocate one opaque reference-counted identity token per logical source occurrence.
Cloning a node preserves its token. Compare and hash token identity consistently,
including ordering, and omit addresses from normal plan display. This avoids a
global identifier allocator or another dependency. The token belongs to one
compiled in-process graph; it is not a restart-stable checkpoint identifier.
Durable preparation still needs stable flow, source, incarnation and attempt
identities with their separately defined recovery contracts.

## A finite consumer may cancel

`LIMIT 0` expresses zero consumer demand. It may complete without opening or polling
its input even though planning preserves the source occurrence. Returning an empty
result from that consumer is cancellation of demand, not proof that its source
reached a final checkpoint.

The existing stream limit can wait for another data event before noticing that
its fetch is exhausted. Empty filtered batches can keep it waiting indefinitely.
Handle zero initial demand before executing the child. Preserve bounded-result
schemas and row counts, and keep later marker/final-checkpoint completion work
separate. A live zero-output filter without a finite consumer remains live.

## Alternatives and evidence required

Special-casing only false filters leaves limit elimination, empty propagation,
union simplification and later optimizer rules able to erase sources. Owning
each pruning rule is possible but increases the maintenance surface. A separate
participation graph could retain identity while pruning data, but would also need
shared source ownership, control routing and protection against double polling.
The existing event-aware nodes provide a smaller coherent boundary.

Verify the actual configured analyzer, logical optimizer, physical optimizer and
worker reconstruction. Controlled sources must prove that zero-output filters
still scan, forward every marker kind in order and propagate source failures.
Observe bounded-source completion and two separate occurrences of the same
provider. Check repeated analysis, aliases, views, unions, expression subqueries,
limit arithmetic, metadata and ordinary batch controls.

Zero-demand tests must prove no child execution or poll, using counters rather
than timing. Preserve failing unchanged-source controls. Run existing public
streaming and scalar-subquery tests, add public regressions, and retain every
unsupported outcome separately from an executed match. Measure planning and
execution costs without removing observability.

Spark 4.2.1 independently protects streaming children from false-filter pruning
and records sources before batch optimization. This supports the distinction
between data pruning and source participation, rather than requiring Sail to
adopt Spark's microbatch architecture. The comparison is source inspection;
executed JVM parity is not claimed.

Does the mandatory compiler boundary preserve all currently admitted streaming paths
without changing batch behavior? The controlled-source and public-query corpus
must settle that before qualification. Which command or opaque-provider entrances
need additional source declarations? Record and test those boundaries rather than
claiming coverage from ordinary table scans alone.

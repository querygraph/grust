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

## Use the analyzer boundary

Sail configures its name/type analyzer separately from its logical optimizer.
Add a final Sail analyzer rule after existing function, type and file-metadata
resolution. It detects declared streaming providers, lowers their admitted
relational graph into the existing flow-event nodes, and leaves ordinary batch
plans on their current path. The ordinary logical optimizer then sees event-aware
extension nodes instead of batch filters and limits that permit source erasure.

Register this rule through the existing session factory. Standard execution,
programmatic session planning and explain planning must use the same rule.
Avoid an execution-only rewrite that makes explain describe a different plan.
Already lowered graphs must remain unchanged when analysis runs again.

Do not run the full relational optimizer as a disguised preparation phase.
Literalize only limit and offset expressions needed by the existing stream-limit
constructor, using public expression simplification with the analyzed schema and
configuration. Preserve negative, null and nonliteral-bound checks. Do not invent
a separate query timestamp to fold time-dependent bounds.

Discover sources through supported aliases, renamed providers, exposed view plans
and expression subqueries. Bounded expression subqueries must retain their batch
semantics and existing physical preparation. A streaming source inside a subquery
must not silently become a batch constant through pruning. Operators without an
admitted streaming implementation must produce a named refusal before their source
can disappear. Test actual supported queries before broadening those refusals.

Commands execute once through their existing ownership path. DataFusion's direct
prepared-statement optimizer bypass is a separate entrance to audit; a registered
analyzer rule alone does not prove that it preserves source participation.

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

Does the final analyzer boundary preserve all currently admitted streaming paths
without changing batch behavior? The controlled-source and public-query corpus
must settle that before qualification. Which command or opaque-provider entrances
need additional source declarations? Record and test those boundaries rather than
claiming coverage from ordinary table scans alone.

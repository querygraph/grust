# ORC ordinary read-format adapter

Sail `03e8783f2164b259f17ed0294af6189053240bf4` assembles the committed ORC
source through Sail's existing listing interfaces. Formatting, strict all-target
Clippy and **224 data-source library tests pass**, including 14 focused adapter
and factory tests. This packet qualifies the library adapter. It does not qualify
public registry/CLI/SDP execution or an ORC writer.

The factory resolves planning and resource options from the existing layers,
captures the driver's host IANA reader zone once into the pinned Java profile,
and captures the normalized session display label separately. Worker scans reuse
the descriptor; they do not rediscover a numeric reader timezone. Host capture is
Sail's selected policy, not a JVM-default observation. The already committed mode
guard remains a separate unit.

Inference selects all eligible listed files, preserving each ObjectMeta for
conditional range reads with the current local pool and bounded metadata options.
Physical empty roots are skipped. Merge disabled selects the first usable schema;
merge enabled combines all usable schemas with the shared Spark semantic merger.
Final duplicate-name validation is recursive, including single-file/first mode.
Errors retain their native or merger cause with file context. Supplied schemas
receive recursive read-nullability normalization and bypass footer inference,
including an explicitly empty schema. Scan construction retains the full requested
table schema, projection, groups/identities, constraints, statistics, limits,
ordering, partitioning and captured settings through the existing OrcSource.

Execution uses the **shared listing/cache** again. Its inventory may be cached;
backend re-listing is not guaranteed. Conditional reads bind each phase to the
identity it received and do not establish a snapshot from inference through
execution. Identityless or replaced objects fail without worker HEAD rebinding.
No metadata cache, custom executor, worker metadata payload, or new resource
policy is added by this unit. Factory and sink write requests explicitly return
`NotImplemented("ORC writing is not implemented")`.

The tests execute real listing/decoder scans and cover usable schemas after eleven
physical-empty roots, late fields and incompatible TIME precision, retained
Spark 4.2.1 TIME metadata, root/nested case behavior and duplicate names, supplied
empty/nullability behavior, partition aliases/pruning, globs/hidden files, exact
identity conditions, local pool/resource caps, projection/limits, scan properties,
reader/display capture and write rejection. Stored full-table partitioning and
projected advertised partitioning are asserted separately.

## Retained failure and correction

The first exact candidate `c49c101383d0eb5af8d35cbfb70c8ca6d5b1df1b` passed
formatting and strict Clippy, then reported **217 passed, 3 failed**. It was not
advanced. Its raw gate, logs, candidate, patch and unresolved observation are
preserved under [attempt-01](attempt-01/); the frozen handoff/source snapshots and
pre-review snapshots remain under [implementation](implementation/).

Two tests called the native writer's unsupported STRUCT branch. They now use
three tiny PyArrow 26-written ORCs (251, 251, 344 bytes), with a retained generator,
file hashes and exact schema/value readback. Independent regeneration reproduced
all three byte-for-byte. These are foreign fixtures, not Spark-written files or
new Spark observations; the separately qualified Spark merge contract supplies
the expected semantics.

The original TIME test inserted files 02–11 after the same context had already
listed 00/01. Shared listing source and DataFusion 55.2's default list cache (1MiB,
infinite TTL) support the cache explanation, but **no original runtime cache-hit
trace was retained**. The corrected test builds all 12 mismatch inputs before its
first listing, requires the actual store listing to contain all 12 and exact late
ObjectMeta, and requires a conditional non-HEAD GET of file 11 before accepting the
unchanged precision-conflict assertion. It also asserts no late GET in first
mode. Those corrected assertions now pass in the final 224-test run. No inference
or cache behavior was changed to obtain that result.

[source-audit.json](source-audit.json) pins the production/cache/writer source
anchors. [fixture-correction](fixture-correction/) retains the source-only diagnosis
and successful independent fixture reproduction as recorded before the Rust
retry. [implementation/HANDOFF.md](implementation/HANDOFF.md) is the unchanged
pre-gate handoff; its pending-gate language is historical and superseded by the
successful [gate.json](gate.json). [provenance.json](provenance.json) inventories
all retained bytes. No failed attempt or stronger assertion was discarded.

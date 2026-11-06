# Preserve streaming projection observability

Streaming projection must remain observable when it replaces ordinary projection.
Operators need output counts, reported output size and computation time to diagnose
stalls and costs. Preserve these through DataFusion's standard metrics and Sail's
existing projection telemetry exporter.

Ordinary projection records baseline metrics and expression-evaluation times. Sail
dispatches the expression exporter by physical node type. A new streaming node can
therefore compute correct results while silently dropping existing observability.
Its smaller recorded cost would also make a performance comparison misleading.

Give each executing partition one stream-owned `BaselineMetrics`. Record output polls
once, counting encoded rows, batches and reported bytes, including markers. Reported
bytes can count shared buffers repeatedly; they do not measure uniquely retained
memory. Keep the baseline alive until stream completion or destruction; dropping
per-run clones can publish completion prematurely.

Time active computation without holding a timer across asynchronous suspension.
Wrap each asynchronous helper poll with the compute timer, then drop it before
returning pending. Time synchronous projection, placeholder creation and result
assembly separately. Waiting for input or an external service is not compute time.

Route `StreamProjectionExec` through Sail's existing `ProjectionMetricEmitter`.
An explicit telemetry dependency on the physical-plan crate is acyclic and follows
the existing typed dispatch. It adds workspace build dependencies, without new
external versions. Global routing by metric-shaped names would change other node
behavior; a registration framework is unnecessary for this one integration seam.

Require an internal mixed-event test with exact output counts, sizes and partition
labels. Require a positive-data exporter test that observes baseline and expression
metrics. Preserve failing controls, avoid duration thresholds, and repeat the cost
comparison with equivalent instrumentation before qualification.

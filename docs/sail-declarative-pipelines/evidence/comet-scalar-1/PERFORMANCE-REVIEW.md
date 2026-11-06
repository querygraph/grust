# Performance review of the scalar plan and human-review compendium

Reviewed the complete `HUMAN-REVIEW.md` and `COMET-SCALAR-ADAPTER.md` against the
saved request in this directory. Read the repository `AGENTS.md`, `LAKESAIL.md`,
`SHEHAB.md`, `CLARITY.md` and `WRITING-RULES.md`. This is a document review;
no source edits, builds or runtime measurements were performed by this reviewer.

## Verdict

No performance-related design blocker was found for the stated standalone
qualification increment. The documents make no adapter-throughput, package-loading
or production-readiness claim. The negative control is still being compiled by
the implementation owner; neither compilation nor test success is inferred here.

The human-review compendium treats earlier performance branches as hypotheses
to check against current code and resolved dependencies. It requires identical
semantics and inputs, retained slowdowns, exact-output checks and disclosed host
conditions. Its distinction between diagnostic shared-host ratios and production
claims is appropriate. It does not trade away marker ordering, failure propagation
or commit fencing to improve measured results.

Its filter-batching recommendation remains an experiment rather than an assumed
speedup. Copies, retained bytes, latency and cooperative polling are explicit
costs to measure. A preceding marker must reach the consumer before evaluation
of later data that can fail. That preserves the contract established by the
foundation checks.

## Retained code and bounded resources

Process-retained library code is separate from retaining function instances,
session state or host-funded memory. The adapter plan states that the registry
retains neither session state nor kernels. The compendium correctly identifies
separation of the existing full package owner as required porting work, rather
than claiming the existing registry already releases sessions correctly.

The standalone loader deliberately retains each admitted opening. Therefore it
does not establish a bound on the count of retained handles or code mappings.
The plan discloses this and requires package admission limits and content identity
before package integration. Keep that boundary explicit in results: successful
result-lifetime tests would prove callback safety under retained code, not bounded
dynamic package churn. Future integration should prevent repeated unbounded
admissions and measure native-memory settlement independently of code retention.

Preserving actual Arrow argument fields and checking output compatibility are
required correctness work. This review does not infer their runtime cost or
claim that the new C boundary is faster than the existing DataFusion route.
The standalone adapter leaves package/worker execution and durable preparation
as separate increments, so it does not silently reduce the full end-state scope.

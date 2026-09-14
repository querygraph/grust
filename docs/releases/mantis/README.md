# Mantis 0.19.0 release preparation

Status: source preparation; final release gates and delivery pending.

This release integrates cancellation-safe LanceDB batching and maintenance with
shared Arrow pipelines, plus cumulative admission before portable DataFusion
result copies. Component/adapter receipts are retained at
`docs/reviews/lancedb-integration-a6bc05a` and
`benchmarks/arrow-pipelines/evidence/result-admission-ff5e895`.

Merged preliminary workspace qualification runs at `b3230b0`; final 0.19.0
source still requires full release verification, packages, registry publication,
book/TextPack rebuild and canonical delivery. Automatic routing and complete
operator accounting remain active goals. Benchmark pins are unchanged.

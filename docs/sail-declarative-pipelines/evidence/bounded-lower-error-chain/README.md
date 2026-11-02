# Bounded lowerer standard error chain

Sail `ae26db1324ab87f10b8ce79dc413dcaed2018246`, parent `bc592d7e3`,
imports Fable `dea394efb82fcb18beac4ed53c109f40648ae99a`. Both lowerer and
test blobs match. LowerError::source exposes BindingError/SparkError; a rejected
plan has evidence and no underlying cause. No dependency or public activation.

Exact detached actual-parent fmt, strict all-target/all-feature Clippy and
134 common-datafusion + 131 Connect libraries pass (265 total). The new test
walks standard sources through LowerError/SparkError/DataFusionError and downcasts
a provider error type the lowerer never names. It also checks binding error type
and rejection None. This qualifies that error path, not every nested cleanup or
transport policy. No new concurrency mechanism/optimized/public CLI verdict.

SHA256.json covers all packet files except itself. Historical receipt/script
paths are not replay destinations; use fresh outputs.

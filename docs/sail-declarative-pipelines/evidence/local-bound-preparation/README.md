# Runner-bound local preparation before planning

Sail `a0a369baada5b3b78d66c11c6694191da72d6fe8`, parent18bfee751, adds the object-safe
JobPreparation capability and a move-only LocalJobPreparation borrowing its runner.
Admission reaches the existing stop-visible map before returning to the caller;
execution consumes the object and reuses the same resource owner. finish/cancel
consume it without converting the caller's typed planning result. Existing local
execute delegates through the object. Other runners keep legacy execution; their
new optional preparation capability returns unsupported until implemented.

The stored SessionContext clone shares authoritative state. TaskContext capture
occurs at execution, preserving late config semantics; it does not create a frozen
operation snapshot. The dynamic trait test mutates authoritative native config
state after admission, rather than exercising an actual SQL/RPC SET command.
Seven new tests cover scope identity/config, admission after stop, cancellation
before physical construction, borrowed !Sync planning with held registered I/O,
retained failed cleanup after Drop, no-stream finish/fresh owner and dropping an
unpolled execute future. The nine original local tests remain unchanged.

Exact fmt/strict Clippy and125 common-datafusion+221 execution+29 session library
tests pass;16 optimized local tests pass under ten joined CPU-load workers.
Admission-bypass control761c11853 changes only the insertion to drop(job): the
identical test fails with registry0 instead of1 (exit101). Initialc3cc4df2f positive
library gate125+220+29 is retained, superseded by the final unpolled-future test.
A rebuilt CLI at the final commit passes300 selected public cases and67 upstream
Python executions, with Spark4.2.1 and the owned server stopped (exit0/no listener).
The first qualifier assumed one rather than two joining newlines around the
unchanged test suffix; correcting that verifier assumption changed no product/test
source. Final source, receipts, test blobs and binary hashes were checked before
conditional branch advancement.

No planning callers are migrated yet. Cluster preparation, operation context/routing,
provider byte/outcome/recovery policy, and complete original Spark SDP acceptance
remain open. These regressions do not prove all original Scala assertions.

Historical absolute paths and binary hashes identify advancement-time evidence.
Use fresh outputs when replaying. SHA256.json covers all packet files except itself.

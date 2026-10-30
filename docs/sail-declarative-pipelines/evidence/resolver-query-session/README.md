# Route queries executed by resolution through the supplied Session

Sail `2e7beda829a107768d0bb00f6d526c6d4d268b30`, parentb90c4fbbe, adds an optional
borrowed query Session to PlanResolver and a private collect_query helper. The four
sites that execute queries during resolution use it: pivot inference, time-travel
scalar evaluation, tail count and crosstab distinct values. The nested stored-view
resolver propagates it. With no supplied view, the exact prior authoritative
ctx.execute_logical_plan(...).collect() path remains. No planner task is spawned,
no scope/context is minted and no session command is redirected to a snapshot.

Five tests invoke the actual helper methods: the four opt-in paths retain a custom
planner/provider, the same resource scope and isolated object-store registry, with
captured native config7 after authority changes to9; the fallback stays on ctx.
The mutation is a direct native config-state mutation, not an actual SQL/RPC SET.
The three data-reading helpers admit an actual GET through the scope; time travel
runs its scalar query without a provider read. The nested-view propagation is
source-reviewed/included in the regression tree, not independently exercised by a
new view/helper fixture. Provider factories and final execution remain separate.

Exact fmt/strict all-target/all-feature Clippy and42 plan-library tests pass.
42 optimized tests pass under ten joined CPU-load workers. Controla63d6fb35 changes
only the helper body to bypass the supplied Session: the same four helper tests
fail for missing task resource scope while fallback passes (exit101,1 passed/4
failed). Identical test blobs, logs, source and optimized binary were qualified
before conditional branch advancement. The rebuilt CLI at this exact commit passes
300 selected public +67 upstream Python executions, Spark4.2.1, and its owned server
stops with exit0/no listeners. This is the latest public regression pin, not full
original Spark Scala SDP acceptance.

Initial420190263 failed on the missing test ObjectStoreRegistry trait import;
that raw Clippy failure is retained. The first qualification wrapper expected the
Rust type name in the missing-extension message instead of its human name. Raw
control results were correct; the corrected qualifier checks their exact receipt
and resumes remaining gates without altering/rerunning the tests. Both scripts are
retained. The control's unused-import warning and historical linker unwind-size
warning are preserved; neither is a passing strict-Clippy claim on the control.

Public callers do not yet supply this view. The API relies on the caller to retain
admission, choose capture after authoritative config mutation, and join cleanup.
Source/write/procedure factories, functions/table functions, final execution-context
transfer, cluster preparation, typed primary/cleanup transport and provider effect
bounds/outcomes/recovery remain open. No general SDK/provider barrier follows from
these helper tests. No dependency change. SHA256.json covers packet files except
itself; historical absolute paths/binary hashes name advancement-time evidence.
Replay into fresh outputs, never overwrite retained receipts. Commit objects are
retained under refs/sdp/evidence.

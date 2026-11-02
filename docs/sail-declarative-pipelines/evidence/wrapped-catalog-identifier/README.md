# Analyzer-time catalog IDENTIFIER resolution

Product 4ab0d74bfa8d02c3a9486f4aaa8bf15e174f1091, parent
f0a232af259fa2bf33c089d5439ffb45fa78061e, routes top-level catalog IDENTIFIER
through existing scalar identifier resolution in an empty schema, with the shared
analyzer-time subquery/type-only stance. The internal flag is renamed from
`table_identifier` to `analyzer_identifier`; table-only missing-column remapping
stays in the table helper. Single-part catalog parsing is shared; bare catalog
behavior remains unchanged. No namespace, lock, Session or function-path changes.

Three native tests cover type-only current/rand/arithmetic/error/UDF arguments,
ANSI on/off, missing-column precedence, multipart parsing and zero UDF invocation.
Detached fmt/strict Clippy and 104 plan +177 Connect tests pass. Unchanged tests
fail0/3 when restoring the old catalog policy and0/1 when restoring table-only
column precedence. A fresh CLI passes300 selected public +67 upstream executions,
four existing parameter tests, and preserves all14 arithmetic +20 provenance
outcomes/metadata. These are not full original Scala SDP-suite acceptance.

The expanded48-case Spark4.2.1 oracle records source/JAR hashes, exact queries,
errors, namespaces and server teardown. The original32 cases improve13→15 behavior
matches (metadata2→4). The reviewed unadvanced table-route candidate16da863ca
matches22/48 behaviors/5 metadata sets; final4ab matches25/48 and8 metadata sets.
All23 remaining behavior differences remain visible. In particular, three SDP
missing-column errors now carry the right inner structured condition but escape
without the outer registration wrapper: the registration callback currently only
catches `SparkError::AnalysisError`. Fix that generic boundary in the next unit,
while leaving structured evaluation errors unwrapped. No flow runs/data writes.

attempt-01 retains an initial borrow type compile failure. attempt-02 retains the
unadvanced table-route candidate, its103+177/public gates, unchanged0/2 control,
32-case replays and48-case review probe. Both owned servers stopped/no listeners;
all observed graph registrations are dropped and session namespaces stay unchanged.
verify.py checks source identity, receipts/log hashes, test blobs/controls, public
counts, exact earlier probe equivalence, comparison accounting and teardown.

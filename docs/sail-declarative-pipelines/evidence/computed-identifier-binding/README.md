# Computed identifier binding qualification

`sdp-fixture-failure` preserves the initial 94-plan / 176-pass, 1-fail Connect
run: the new catalog-path regression required a DataSourceRegistry extension
missing from the minimal test fixture. Adding that registry changes no assertion.

This packet follows the literal normalization at ccb6fb212. It distinguishes
computed target lookup from early graph-input substitution, preserving native CTE
precedence and stored-view namespace capture. Native policy and SDP wiring are
separate review units. No Connect-reference freeze representation is activated.

The namespace oracle defines a graph in binding_a then switches the ordinary
session to binding_b: early named/literal reads retain foo9 from A, computed CONCAT
reads foo10 from B. The session remains in B. The initial Spark-only harness and
its results are preserved; the engine-parameter adaptation is rerun against Spark
before Sail. This compares rows and namespace, not full diagnostic metadata.

`native-initial` passed before adding a separate late-qualification policy; it is
superseded by `native`. `native-before-stronger-test` retains a successful gate
whose missing-table test failed to detect the namespace bypass;
`namespace-control-vacuous` records that passing mutation. The stronger test
requires a real catalog view with a distinct output column. `control-filter-failure` retains an invalid control run
that selected zero tests. The corrected controls use the Rust module filter and
leave the test source unchanged. Both lookup and namespace bypasses must fail the
opt-out test while preserving the default-scope test.

Expression-subquery Spark probes both return NOT_A_CONSTANT_STRING.NOT_CONSTANT,
even with incorrect column case; the printed unresolved subtree has substituted
the graph view. This is evidence for a remaining helper-diagnostic ordering gap,
not a claim that this patch fixes it. SQLWithRefs capture and generic plan-ID
references remain separate unfinished design/implementation work.

`verify.py` checks the archived hashes, exact source ancestry, library counts,
unchanged controls, public results and feature comparisons. The 300 selected public
cases and 67 upstream Python executions do not cover the full original Scala SDP
suite. The full user goal remains active.

Qualified commits: native d2ada245e5464fee71782332419e76b525499402 (94+176 libraries),
SDP dd4c9344adc063d73e8350cf77002c075d0dd49c (94+177 libraries); formatting and
strict Clippy pass. Fresh public300+67 pass. Dynamic13/13 and namespace3/3 match;
expression diagnostics differ0/2 and remain required work. The source commits
were advanced only after their exact receipts and unchanged controls passed.

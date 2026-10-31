# Structured catalog analysis errors during SDP registration

Product4761d0064b592f66647dec807801c57fcfc546c9 follows resolver commit
4ab0d74bfa8d02c3a9486f4aaa8bf15e174f1091. The seven-line production change
classifies the existing structured AnalysisException alongside string analysis
errors during catalog directive preparation. Structured arithmetic/evaluation
errors still escape unchanged, matching Spark's AnalysisException-only handler.
No PlanResolver, namespace, graph-lock or Session behavior changes.

The existing native preparation test now exercises all three actual wrapped
missing-column expressions through PlanResolver. A new prepare/commit test checks
structured analysis wrapping, structured arithmetic preservation and absence of
partial graph registration. Detached fmt, strict Clippy and all178 Connect tests
pass. Removing the production arm makes the unchanged boundary test fail0/1.
The plan crate's source is byte-identical to the parent that passed104 plan tests.

A fresh exact-source CLI passes300 selected public tests,67 upstream Python
executions and four existing parameter tests. All14 arithmetic and20 provenance
outcomes/metadata remain unchanged. On the same48-case Spark4.2.1 oracle, behavior
matches improve25→28 (metadata remains8). The three corrected cases are SDP
wrapped missing, missing after current_catalog, and typeof(missing): each now
contains both PIPELINE_SQL_GRAPH_ELEMENT_REGISTRATION_ERROR and its original
UNRESOLVED_COLUMN condition. No previously matching case regresses. All20
remaining behavior mismatches are retained; full original Scala SDP acceptance
is still unqualified. No flows run or data writes; owned servers stop/no listeners.

attempt-01 preserves the initial test compilation failure from a missing explicit
StructuredSparkError import; production source is unchanged in the qualified
candidate. Source, log hashes, unchanged test blobs, fresh CLI/artifacts, probes,
comparison accounting and teardown are checked by verify.py and SHA256.json.
The48-case probe and Spark source/JAR observations are in the preceding
[wrapped catalog packet](../wrapped-catalog-identifier/README.md).

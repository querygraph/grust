# Original two-namespace materialized-view assertions

Test-only Sail commit8e5e06ff48a5458fb6d68e4d82ca147f634e406e ports Spark4.2.1
SqlPipelineSuite:562–579. Both original materialized-view statements register in
one SQL file, with the second database-qualified output reading the first.
One run completes, and both qualified outputs return Row(1). Unique database
names adapt isolation; graph/table/database cleanup is verified.

The identical9 tests (new case, four namespace-scope cases, four batch-CTE cases)
pass on Spark4.2.1 and Sail. The original assertion source pin is
617618396087429b5627a86ce933bb0f5d6645cb. Ruff0.17.3
check and format pass on the detached exact test commit.

Runtime uses the already-qualified d99e8b86d CLI artifact. Its SHA is checked
against the ANSI-nullability public receipt; Git proves that8e5 changes only
the two Python test/fixture paths. No rebuilt8e5 binary or new native test verdict
is claimed. Current memory/memory catalog_scope.py also passes all7 outputs
(5 original assertions plus2 input checks), provider/schema metadata, private
view isolation, session defaults and cleanup. The historical memory/LakeCat
profile remains at8d044db386 and is not claimed as a fresh run.

The first84d candidate passes Sail but Spark fails all9 cases in setup:
spark.sql.warehouse.dir is static. The corrected fixture catches only
AnalysisException/CANNOT_MODIFY_STATIC_CONFIG; Spark uses its isolated startup
warehouse, Sail keeps its existing per-session override, and other errors
propagate. The test body is unchanged. Both attempts and raw reports are retained.

Inventory mapping changes only SqlPipelineSuite:562, unmapped to partial.
The62 partial/400 unmapped total retains97 reviewed/462 static sites.
The crosswalk also reconciles its stale materialization table with the existing
canonical inventory (10 partial/17 unmapped); that is not new materialization
coverage. Original Scala-suite execution remains false.

manifest.json hashes raw evidence; verify.py checks source/fixture hashes,
paired JUnit counts, the prior setup failure, exact reused binary identity,
test-only source equivalence, all catalog assertions/cleanup and inventory delta.

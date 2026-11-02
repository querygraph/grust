# Spark ANSI primitive string-cast nullability

Sail d99e8b86d4db7aa2c5f79848496e6f3bfad6acb2, parent e18c7a81a, makes
SparkAnsiStringCast return a nullable field for all seven supported targets.
Spark4.2.1 pin617618396087429b5627a86ce933bb0f5d6645cb defines
Cast.forceNullable(StringType, primitive) as true (Cast.scala:428–434);
Cast.nullable uses that rule even in ANSI mode (:630–640). The former unit test
incorrectly used DataFusion Cast as the nullability oracle.

Production changes are one field flag and its explanatory comment. Ordinary
metadata is retained and extension metadata removed as before. Parsing, values,
structured errors, target domain, resolver routing and worker payload are unchanged.
Native field tests cover84 combinations: seven targets, three string layouts,
two input nullabilities, scalar-known/unknown arguments. Decoded worker fields
are checked for all seven targets.

Exact detached gates:410 function +243 execution +123 plan tests, formatting,
strictClippy. A production-only return-field revert retains the exact test blob
and fails0/1. Fresh final CLI passes300 selected public and67 upstream Python
executions. Spark and Sail each pass21 conditional/cast feature scenarios,
including the three new literal/non-nullable-column/nullable-column schemas.

Fresh90-case SQL comparison covers CAST/TRY_CAST, two ANSI settings, seven
primitive targets, literal/non-nullable/nullable inputs and three NVL2 shapes.
All90 rows match; complete schemas improve64 to79. All14 direct ANSI CAST
failures close. One NVL2 case closes; eight legacy primitive CAST and three
NVL2 schema cases remain. This does not establish malformed legacy parsing or
general CASE/folding parity.

The initial c269dabc7 candidate failed test compilation because sail-execution
does not depend directly on datafusion_expr. It is retained under attempt-01;
final changes only that test import to DataFusion's public re-export, with
independent final gates. Fablefc51ebf3 accepts the production change.

manifest.json hashes raw evidence; verify.py checks exact pins, hashes, test
counts, unchanged-test control, CLI identity, both feature runs,90-case results,
remaining failures and the retained failed attempt. The regression selections
are not full original Scala SDP acceptance.

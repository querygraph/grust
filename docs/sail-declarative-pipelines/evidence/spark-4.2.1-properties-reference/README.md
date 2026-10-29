# Spark 4.2.1 pipeline table properties

`probe.py` ran six SQL pipeline scenarios against the Spark 4.2.1 local Connect
JVM and Sail source `a007290e7a628c0b9da373b4490431147134e94e` through port 50082.
The Spark source reference is `617618396087429b5627a86ce933bb0f5d6645cb`.
Raw results and logs are retained. These are observations of differences, not a
passing Sail compatibility gate. Both engines reported version 4.2.1.

| Input | Spark | Sail before correction |
| --- | --- | --- |
| Unknown `pipelines.unknown`, plus custom property | Drops unknown key; retains custom property | Retains both |
| `PIPELINES.RESET.ALLOWED=false` | Stores canonical lowercase key | Stores original uppercase key |
| `pipelines.reset.allowed=maybe` | IllegalArgumentException; target absent | Succeeds |
| Same invalid value, dry run | IllegalArgumentException; target absent | Succeeds without publication |
| `PIPELINES.RESET.ALLOWED=maybe` | Succeeds; stores lowercase key and invalid value | Succeeds; stores uppercase key |
| `pipelines.reset.allowed=' TRUE '` | IllegalArgumentException; target absent | Succeeds |

The case asymmetry follows the source: `PipelineTableProperty.fromMap` looks up
the exact canonical key. `GraphValidations.validateTablesAreResettable` calls it
for every table during graph validation, including dry runs. Later,
`PipelinesTableProperties.validateAndCanonicalize` iterates case-insensitively,
but its value check again reads the original map by the canonical key. A mixed-case
key can therefore bypass value validation before being stored under the canonical
key. Preserve the distinction when implementing the compatibility path; do not
canonicalize the input map before graph validation.

Next implementation: validate the exact canonical reset key during graph
analysis; filter unknown pipeline properties and canonicalize recognized keys
during table materialization. Reset-policy graph constraints and streaming reset
behavior require additional coverage beyond these six batch observations.

The initial Spark probe attempted to set the static warehouse configuration
after session creation and failed before running any scenario. Its script and
log are retained as `probe-before.py` and `spark-before.log`. The corrected probe
sets the warehouse on the Spark builder. The Sail baseline used the earlier
script; its scenario bodies are identical and its session accepts that setting.

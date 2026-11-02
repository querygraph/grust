# Planning context authority characterization

Design-only candidate `27b82ad2588696973a232660e2affcb8153409a3` on production
basebebabdb9e adds only a temporary test module/declaration. It is retained under
refs/sdp/design-probes/planning-context and is not imported into the product branch.
probe.rs is byte-identical to that candidate's test source.

Three native-path tests pass and emit DESIGN_PROBE JSON observations:

- Builder snapshots share catalogs but copy config/UDF maps and reset session ID.
  Child table registration reaches the parent; child native SET reaches9 while
  parent remains7; child DataFusion UDF registration does not reach the parent.
- Restoring original configuration before build replaces the shared default
  catalog; an existing parent table disappears.
- Restoring config after build and explicitly setting ID preserves catalog,
  runtime and existing UDF Arc identity, but native SET still affects only child
  state. This is not an authoritative context wrapper or an approved helper.

Initial981f631a1 fails compilation because SessionContext.sql is unavailable under
Sail's DataFusion feature set. The corrected test uses native SetVariable through
execute_logical_plan, matching Sail's existing native statement route. No SQL
feature/dependency was enabled to make the probe pass. Both logs/receipts remain.
Sail's own CatalogManager functions use shared manager state: do not generalize
DataFusion-UDF behavior into a claim about every Sail function command.

This is dependency/source-design evidence, not original Spark SDP acceptance,
planning ownership, full configuration preservation or a production context API.
[Design checkpoint](../../PRE-PLANNING-OWNERSHIP-DESIGN.md) separates observations
from the selected lifecycle direction and unresolved authority/memory APIs.
Historical receipts preserve original /tmp paths. SHA256.json covers this packet
except itself; replay against fresh immutable source/output paths.


ServerSessionFactory normally disables DataFusion default catalog creation and
omits its default features in favor of Sail's catalog/function machinery; workers
add default features. The rebootstrap probe uses a default DataFusion context,
so it is not evidence that a normal Sail server currently loses its catalog.
It constrains general/custom-mutator snapshot preservation and the proposed API.

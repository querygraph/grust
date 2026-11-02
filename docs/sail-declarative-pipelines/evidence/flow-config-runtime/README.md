# Flow configuration runtime integration

This packet retains the implementation, failed attempts, controls and differential
observations for Spark 4.2.1 flow configuration inheritance. It does not establish
full SDP acceptance, captured provider ownership or streaming/CDC execution.

## Review units

1. `b4d83ef728910a00e8564c1991c8024a9a22fc15`: native query source schema case
   matching is independent of semantic column matching. Ordinary callers retain
   their defaults; stored-view child resolvers preserve the optional override.
   Exact fmt, strict Clippy and 88 Plan + 151 Connect library tests pass.
   Two independent unchanged controls each fail both new tests (0 pass / 2 fail):
   bypass the getter, or drop the stored-view child copy. The fixtures traverse
   real factories, direct source/format path/catalog table/catalog view routes,
   captured and legacy sessions. They do not scan data or qualify SDK ownership.
2. `349771bd9445eb847904ce57659ab8baf07a315c`: import Fable's pure map arithmetic
   from `164058355ce2bd52214339a4092d519abf2ea859`. Declared and accepted raw maps
   remain distinct; repeated ordered contributions overwrite first-pass values;
   successful analysis alone permits conflict checking and a conditional second
   call. Display names never deduplicate canonical inputs. Exact combined gates:
   fmt, strict Clippy, 88 Plan + 166 Connect tests. Fable's earlier full-library
   164-pass/2-fail run without importable PySpark is not counted as a full pass;
   the root gate uses explicit Python 3.12 / PySpark 4.2.1 paths.
3. `fa78d067cd20c9ca3a3d1c29055eeb53633a22bd`: ordered input discovery with shared
   GraphScope name qualification, initial-config CTE scopes, repeated inputs,
   expression subqueries and native registered-format exclusion. Four real-parser
   test groups cover order, CTEs and canonical multipart identities. No runtime
   configuration behavior changes in this unit. Exact gates are archived below.
4. `1bc9d15620dd4c85ac3f09ff8ec90d5b92a4292e`: runtime activation uses the tracer,
   native first semantic pass, success-only raw-map merge, structured
   DUPLICATE_FLOW_SQL_CONF, and conditional new analysis call. Accepted maps are
   keyed by flow identity and used for command input reanalysis and writes.
   Working plans remain local; exports contain schemas/publications/config maps.
   The exact Rust, rebuilt public and differential receipts were verified before
   conditional branch advancement; the product worktree is clean.

The source tree of activation candidate 1bc9d1562 equals the independently gated
17d671c98 candidate; history was split into trace and activation review units.
The final commit received its own exact gates and rebuilt CLI verdict.

## Evidence and differential boundary

- `source-read-case-ready/`, `native-controls/`: source case gates and controls.
- `config-merge-import/`: root combined pure-module gate.
- `flow-config-trace/`: isolated trace gate.
- `flow-config-activation/`: final runtime candidate and Rust gates.
- `flow-config-public-1bc9d1562/`: fresh CLI build and frozen 300 selected public
  tests plus 67 upstream Python executions. These are not original Scala suites.
- `flow-config-matrix-1bc9d1562/`: unchanged thirteen-case public probe, compared
  with the pinned Spark results in the adjacent historical reference packet.
- `comparison-1bc9d1562.json`: eight matching error-condition/success-row outcomes,
  five differences. This comparison does not assert exact conflict provenance,
  full error messages or arbitrary private-configuration semantics.
- `flow-config-public-c43bfd68e/`, `flow-config-matrix-c43bfd68e/`, and
  `comparison-c43bfd68e.json`: earlier candidate receipts, preserved as historical
  evidence. The native-form regressions below were added after this candidate.

The five differences are upstream_true, left_false_right_true, repeated_last_true,
transitive_raw_conf and external_read_after_true. Both engines fail those queries,
but Sail lacks Spark's UNRESOLVED_COLUMN.WITH_SUGGESTION structured condition.
All five expected configuration conflicts and all three success rows now match
at the comparison's stated scope. Inputs and session settings are verified equal.
The owned servers exited zero and left no listeners.

## Retained failed attempts

- `source-read-case-attempt-01/`: tests called a private resolver helper; compile
  failed. Replaced with the real public catalog-view route.
- `source-read-case-attempt-02/`: test Mutex poison error retained a borrowed
  guard; compile failed. Converted that diagnostic to an owned string.
- `flow-config-runtime-attempt-01/`: missing test HashMap import and Clippy's
  large-enum warning. Added the import and boxed the resolved result.
- `failed-box-format.rs.txt`: intermediate invalid delimiter during the box edit;
  formatter rejected it. No source verdict was assigned to that invalid file.
- `flow-config-runtime-attempt-02/`: 88 Plan pass, 169 Connect pass / 1 fail.
  A source-free clock fixture had no DataSourceRegistry. Registry lookup became
  optional for source classification, preserving the native failure if needed.
- `flow-config-runtime-ready/`: passing 88 + 173 intermediate candidate.
- `flow-config-runtime-counted/`: passing 88 + 174 candidate; adds actual native
  factory call counts (changed accepted map: two calls; equal map: one call).
- `flow-config-native-regression/`: unchanged native dynamic-identifier and
  WithRelations fixtures fail 0/2 without the no-view-settings path.
- `flow-config-runtime-native/`: those exact fixtures pass in a full 88 + 176
  gate before the history split. No failing assertion was loosened.

## Remaining requirements

- Configured DynamicTable, WithRelations and opaque plan-ID references need real
  binding support. The tracer explicitly refuses these forms. When no graph view
  declares settings, native resolution bypasses the unnecessary trace, preserving
  existing dynamic/parameter-relation support. Table-only settings do not force it.
  An unrelated configured view can still force tracing: general parity is open.
- CTE recursion/legacy policy, native-versus-trace case matching and exotic
  metadata expressions require direct qualification; structural traversal alone
  is not proof of Spark binding equivalence.
- A command whose private configuration changes its input closure needs further
  implementation/qualification. Missing command view inputs currently fail.
- Only ORC currently consumes SourceInfo.read_case_sensitive. Parquet and other
  format implementations need metadata case matching/duplicate-column support.
  Fable's review `439df325` caught this limitation; the native seam is not a claim
  that the external Parquet duplicate-column oracle is satisfied.
- Generic native structured unresolved-column errors remain separate Sail work.
- Captured physical preparation, planning admission, provider/SDK lifetime,
  shutdown, streaming/Iggy/CDC durability and original Scala acceptance remain.

Run `verify.py` to check the packet hashes, exact source receipts, test counts and
comparison boundary. `run-matrix.py` requires the qualified immutable CLI and a
fresh output directory; it deliberately refuses source/binary drift.

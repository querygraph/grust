# Internal Table metadata: creation and ordinary refresh

Sail candidate `a9eecf5f539115ceb2b604d26d72b058cf9c435d`, parent
`db650c40e7605658b047fafac2fc721a395c4a0c`.
[Design and remaining work](../../METADATA-TABLE-MATERIALIZATION-DESIGN.md).

The private materializer now handles streaming Table creation and ordinary
refresh using existing catalog commands. Existing Table rows are retained,
existing-left schemas merge, new fields append and properties update. Public
execution still rejects Table/Sink before metadata effects. Allowed streaming
full reset is explicitly unsupported before mutation; reset.allowed=false
uses ordinary refresh. This does not activate streaming or CDC.

- Exact detached formatting/strict Clippy/[native library](native/rust.log):
  189 passed, zero failed/ignored. Four new tests cover two original assertions,
  row retention/merge/comments/properties, disabled reset, incompatible schemas,
  partition mismatch, full-reset preflight and the execution guard.
- [Production-only control](control/control.json): skipping Table metadata with
  unchanged tests makes all three behavior tests fail; the guard test passes.
- [Fresh public receipt](public/receipt.json): 300 selected tests and 67 upstream
  Python executions passed against an exact freshly built CLI; owned server stopped.
- [Spark metadata adapter](spark/internal-materialization/MetadataOracle.scala):
  unmodified original registration helper, production DatasetManager, Spark4.2.1.
  Reproduces MaterializeTablesSuite:125 and :374 catalog assertions, preserving
  Table kind, and additionally checks zero rows. Compile/JAR/run logs retained.
- [Spark ordinary-refresh reference](spark/internal-refresh/RefreshOracle.scala):
  retains an existing row, left field order/comments, adds the new field and
  sets properties. Backend is Spark's default session catalog; Sail uses memory
  catalog with real Parquet data. No fresh LakeCat alter verdict is claimed.

The native fixture resolves real independent batch query schemas directly,
without changing Table output kinds. Full execution analysis deliberately still
rejects those batch Table flows. The guard fixture supplies resolved metadata to
exercise rejection; it is not evidence that public analysis accepts them.

Two inventory sites move unmapped → partial: 65 partial/397 unmapped among462
static registrations,97 assertion-reviewed. No original ScalaTest suite ran
against Sail. Full original JVM integration, wrapped materialization errors and
origins, normalized-path propagation, backend coverage and owned full-reset
auxiliary cleanup remain open.

Five discarded candidates and their raw receipts/logs remain under
failed-attempts: compile shadowing, disallowed SQL LOCATION fixture, its repeated
attempt after a fixture-edit wrapper failed before writing, execution-analysis
flow-kind rejection, and a private-method fixture compile error. The standalone
Spark adapter's initial bad companion import failure is also retained. Assertions
were preserved; the fixture now configures a private warehouse and uses the
metadata schema seam. Successful native runs clean their data directories.

Fable source reviews: CF-0443/Grust667a4720 and CF-0445/Grust94935dfb.
The latter accepted the exact candidate pending the gates, now recorded here.
Existing ASCII reset parsing's long-s edge is not fixed by this change.

Run `python verify.py` with the local Sail/Spark Git object stores available.

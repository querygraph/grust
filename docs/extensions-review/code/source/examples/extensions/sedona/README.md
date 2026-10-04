# Apache SedonaDB extension proof of concept

Start with the [source-distribution tutorial](../TUTORIAL.md) for a fresh install,
local and distributed deployment, and executable review examples.

This independent Python wheel exposes **128 native Apache SedonaDB scalar
functions**, plus their aliases, to Sail through DataFusion's scalar-UDF capsules.
The functions combine SedonaDB's native Rust implementations with its GEOS
kernels. Geometry construction, text conversion, predicates, distances, and
other registered operations execute in native code. No Sail crate is a dependency.

The source is Apache SedonaDB commit
[`0a1993d9be8bcf52150593ad08fc6a3412d50f29`](https://github.com/apache/sedona-db/tree/0a1993d9be8bcf52150593ad08fc6a3412d50f29).
`patches/datafusion-55.patch` pins its workspace to DataFusion **55.1.0** and
Arrow **59.3.0**, and ports the envelope aggregate's `GroupsAccumulator` contract
required to compile the scalar crate. `Cargo.lock` pins the independent wheel's
complete dependency graph. The package uses PyO3 **0.29.0**.

## Build and check

Requirements: Rust 1.95 or newer, Python 3.12, `maturin`, a C compiler, and GEOS
3.12 or newer discoverable through `geos-config`. Build receipts record the
actual toolchain/library versions. On Linux maturin repairs shared dependencies;
on macOS an explicit delocate step bundles GEOS. Repaired wheels carry the
minimum OS tag required by their actual libraries, not a guessed older target.
The branch build script verifies bundled dependency paths before installation.

```sh
cd examples/extensions/sedona
python3 scripts/prepare.py
export CARGO_INCREMENTAL=0 CARGO_BUILD_JOBS=4 CARGO_PROFILE_DEV_DEBUG=0
export CARGO_TARGET_DIR=/tmp/sedona-extension-target
export PYO3_PYTHON=/opt/homebrew/bin/python3.12
maturin build --locked --interpreter "$PYO3_PYTHON" --auditwheel repair --out dist/raw
# macOS (install the locked delocate build dependency first):
python -m delocate.cmd.delocate_wheel -w dist/repaired dist/raw/*.whl
python ../scripts/check_wheel.py dist/repaired/*.whl
uv pip install --python "$PYO3_PYTHON" dist/repaired/*.whl
python scripts/smoke.py
cargo test --locked
```

For both platforms, prefer `examples/extensions/scripts/build.sh` from the Sail
root; it selects the appropriate repair steps and installs only repaired wheels.

Use the Python executable in the Sail server environment for installation and
the smoke test; adjust `PYO3_PYTHON` to that interpreter when building elsewhere.
The source preparation script is idempotent, uses a relative ignored `.deps`
directory, refuses a different revision, and applies a checked patch. It never
needs a local Sedona checkout at an absolute path.

The entry point `pysail.extensions/sedona` yields `sail_sedona:extension`.
`manifest()` is pure Python so the host can reject a version mismatch before
importing the native module or reading capsules. `bind(session_id)` returns a
native session owner; `scalar_udfs()` returns objects implementing
`__datafusion_scalar_udf__()`. Every capsule is named `datafusion_scalar_udf`.
The host must retain the bound owner and register primary names and aliases.

Rust tests force DataFusion's foreign-UDF path even inside the test binary. They
exercise geometry metadata across construction, GEOS intersection and text
conversion, plus null geometry and aliases. The wheel smoke test checks exact
manifest versions, entry-point discovery, all 128 capsule names and the native
session binding. Sail integration tests exercise the separately compiled wheel
through Spark Connect.

Additional regressions compare the ported envelope accumulator's bypass state
against partial updates with nulls, filters and an empty group, and verify that
native-kernel panics become errors before crossing the scalar FFI boundary.

## Scope and next increment

The first PoC supports scalar spatial SQL and correct spatial joins through
Sail's existing general join operators. It does **not** install Sedona's indexed
`SpatialJoinExec`; query correctness is the baseline for the subsequent indexed
join extension. No spatial-join performance claim follows from the scalar build.

Only the listed native Rust/GEOS function sets are exported. This does not
include SedonaDB's complete scalar catalog, raster functions, aggregate exports,
GeoParquet readers, PROJ CRS services, or Spark geometry UDT collection. Return
`ST_AsText`/`ST_AsBinary`, booleans, numbers, and counts to the client. Functions
requiring an absent optional service return the underlying Sedona error.

The host's collision policy forbids shadowing built-ins. Five otherwise available
SedonaDB UDFs and their aliases are therefore omitted: `st_asbinary`,
`st_geomfromwkb`, `st_geogfromwkb`, `st_setsrid`, and `st_srid`. Sail retains its
first three built-ins and its existing `st_setsrid`/`st_srid` placeholders; this
package does not make those placeholders functional. Other constructor aliases,
including `ST_GeomFromText` for `ST_GeomFromWKT`, remain native SedonaDB functions.
The extension does not silently override these names.

Each bound session uses immutable default Sedona options. DataFusion FFI carries
string configuration, but cannot carry Sedona's typed CRS/runtime services.
Host `SET sedona.*` propagation is not implemented. Worker discovery and task
codecs are implemented for actor workers and separate Sail worker processes;
the scalar expressions use `placement: any`. Geometry composition regressions
cover dynamic WKB, CASE/coalesce, array extraction and shuffles. Platform and
deployment qualification must use the exact candidate's receipts, as recorded in
the [follow-up plan](../../../docs/development/extensions/datafusion-graph-plan.md).

The indexed-join increment needs the proposal's physical join hook, function
ownership matching, `JoinFilter` side/index remapping, retained residuals,
input requirements, build-side sharing and an extension codec. The SedonaDB
DF55 port additionally needs `GroupsAccumulator` changes in the convex-hull
crate, the new `ExecutionPlan::apply_expressions` implementations, planning
against `dyn Session`, and `PhysicalPlanningContext` propagation through the
planner. These are separate from the scalar-only patch delivered here.

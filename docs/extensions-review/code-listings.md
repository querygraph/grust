# Complete code and reading path {#code-listings}

## The small author sample {#sample-path}

Read the first five listings consecutively: the native adapter, its Python
bootstrap, the two package manifests, and the spatial SQL/shuffle client.
The first four total 246 lines. The client is copied verbatim from the pinned
tutorial; its import of `functions as F` is retained even though this example
uses SQL strings. Expected assertions are distance 5.0 and distances 0 through
16 after repartition. These are expectations in the existing example, not a
new execution result from this documentation build.

Every printed source file below is complete. The client is the complete Python body of the tutorial example; server
startup is its complete shell block. Their source line intervals are recorded. Rust, Python, TOML, shell, protobuf and patch listings have
language tags for color syntax rendering. Long lines may wrap in exported
editions; the source bytes are preserved in the Markdown and code bundle.

## Running the sample {#running-the-sample}

Use a dedicated checkout with Rust 1.97.1, shared-library Python 3.12, uv,
protoc and a C/C++ toolchain; Sedona also needs GEOS 3.12 or newer. The pinned
tutorial describes platform setup. Review these commands before running them:
the original build script synchronizes its virtual environment and builds both
Sedona and Nutmeg. This document does not run it.

```bash
git clone https://github.com/querygraph/sail.git sail-extension-review
cd sail-extension-review
git checkout --detach bd8ce9ae8839477e2c08a0475ab7900b115c5366
bash examples/extensions/scripts/build.sh
.venv/bin/python examples/extensions/sedona/scripts/smoke.py
```

In terminal A use the complete [server startup](#listing-server-start) listing.
In terminal B save the [client](#listing-sedona-client) as a Python file and run
it with `SPARK_CONNECT_MODE_ENABLED=1 .venv/bin/python <client-file.py>` from
the checkout. Stop the server before changing execution modes. To exercise
separate workers, retain the startup exports and change its final launch to
`SAIL_MODE=local-cluster SAIL_EXPERIMENTAL_PROCESS_WORKERS=1` followed by the
same executable and arguments. A local shuffle alone does not prove remote
worker execution; placement must be observed in the selected deployment.

The code bundle preserves the original file paths, complete Cargo lockfile,
licenses and notices, and a SHA-256 manifest. Third-party library implementations
are pinned dependencies, not reprinted here. The much larger Sail integration
is documented separately in the [host implementation companion](../extensions-host-review/manuscript.md).
That companion includes the complete historical host patch, with a comparison
against the separately pinned plain-Sail revision.

## Listings {#sample-listings}

### The native scalar adapter {#listing-sedona-lib}

Source: [examples/extensions/sedona/src/lib.rs](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/examples/extensions/sedona/src/lib.rs). 170 lines.

```rust
//! The extension is an independent dynamic library with no Sail crate dependency.

use std::panic::{catch_unwind, AssertUnwindSafe};
use std::sync::Arc;

use datafusion_common::config::ConfigOptions;
use datafusion_common::{Result, ScalarValue};
use datafusion_expr::{ColumnarValue, ScalarUDF, ScalarUDFImpl};
use datafusion_ffi::udf::FFI_ScalarUDF;
use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use pyo3::types::PyCapsule;
use sedona_common::SedonaOptions;
use sedona_expr::scalar_udf::{ScalarKernelRef, SedonaScalarKernel};
use sedona_schema::datatypes::SedonaType;

/// FFI 55.1 cannot preserve Sedona's typed runtime services in ConfigOptions.
/// Each bound session therefore captures an explicit, immutable Sedona default
/// snapshot. Session SET propagation is outside this local proof of concept.
#[derive(Debug)]
struct SnapshotKernel {
    inner: ScalarKernelRef,
    options: Arc<ConfigOptions>,
}

fn guarded<T>(call: impl FnOnce() -> Result<T>) -> Result<T> {
    catch_unwind(AssertUnwindSafe(call))
        .unwrap_or_else(|_| datafusion_common::exec_err!("Apache SedonaDB native scalar panicked"))
}

impl SedonaScalarKernel for SnapshotKernel {
    fn return_type(&self, args: &[SedonaType]) -> Result<Option<SedonaType>> {
        guarded(|| self.inner.return_type(args))
    }

    fn return_type_from_args_and_scalars(
        &self,
        args: &[SedonaType],
        scalars: &[Option<&ScalarValue>],
    ) -> Result<Option<SedonaType>> {
        guarded(|| self.inner.return_type_from_args_and_scalars(args, scalars))
    }

    fn invoke_batch(
        &self,
        arg_types: &[SedonaType],
        args: &[ColumnarValue],
    ) -> Result<ColumnarValue> {
        guarded(|| self.inner.invoke_batch(arg_types, args))
    }

    fn invoke_batch_from_args(
        &self,
        arg_types: &[SedonaType],
        args: &[ColumnarValue],
        return_type: &SedonaType,
        rows: usize,
        _host_options: Option<&ConfigOptions>,
    ) -> Result<ColumnarValue> {
        guarded(|| {
            self.inner.invoke_batch_from_args(
                arg_types,
                args,
                return_type,
                rows,
                Some(&self.options),
            )
        })
    }
}

#[pyclass(skip_from_py_object)]
#[derive(Clone)]
struct NativeScalarUdf {
    inner: Arc<ScalarUDF>,
}

#[pymethods]
impl NativeScalarUdf {
    fn name(&self) -> &str {
        self.inner.name()
    }

    fn aliases(&self) -> Vec<String> {
        self.inner.aliases().to_vec()
    }

    fn __datafusion_scalar_udf__<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyCapsule>> {
        PyCapsule::new_with_value(
            py,
            FFI_ScalarUDF::from(Arc::clone(&self.inner)),
            c"datafusion_scalar_udf",
        )
    }
}

#[pyclass]
struct BoundSedona {
    #[pyo3(get)]
    session_id: String,
    functions: Vec<NativeScalarUdf>,
}

#[pymethods]
impl BoundSedona {
    #[new]
    fn new(session_id: String) -> PyResult<Self> {
        let mut set = sedona_functions::register::default_function_set();
        for (name, kernels) in sedona_geos::register::scalar_kernels() {
            set.add_scalar_udf_impl(name, kernels)
                .map_err(|e| PyRuntimeError::new_err(e.to_string()))?;
        }
        let mut options = ConfigOptions::new();
        options.extensions.insert(SedonaOptions::default());
        let options = Arc::new(options);
        let mut functions: Vec<_> = set
            .scalar_udfs()
            // The first host policy rejects built-in shadowing. Omit the
            // complete UDF (including aliases) when any name would collide.
            .filter(|function| {
                const BUILTINS: &[&str] = &[
                    "st_asbinary",
                    "st_geomfromwkb",
                    "st_geogfromwkb",
                    "st_setsrid",
                    "st_srid",
                ];
                !BUILTINS.contains(&function.name())
                    && !function
                        .aliases()
                        .iter()
                        .any(|name| BUILTINS.contains(&name.as_str()))
            })
            .map(|function| {
                let kernels = function
                    .kernels()
                    .iter()
                    .map(|kernel| {
                        Arc::new(SnapshotKernel {
                            inner: Arc::clone(kernel),
                            options: Arc::clone(&options),
                        }) as ScalarKernelRef
                    })
                    .collect();
                NativeScalarUdf {
                    inner: Arc::new(function.clone().with_kernels(kernels).into()),
                }
            })
            .collect();
        functions.sort_by(|a, b| a.inner.name().cmp(b.inner.name()));
        Ok(Self {
            session_id,
            functions,
        })
    }

    fn scalar_udfs(&self) -> Vec<NativeScalarUdf> {
        self.functions.clone()
    }
}

#[pymodule]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<BoundSedona>()?;
    module.add_class::<NativeScalarUdf>()?;
    Ok(())
}

#[cfg(test)]
mod tests;
```

### Discovery and binding {#listing-sedona-bootstrap}

Source: [examples/extensions/sedona/python/sail\_sedona/\_\_init\_\_.py](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/examples/extensions/sedona/python/sail_sedona/__init__.py). 23 lines.

```python
"""Apache SedonaDB functions exported through the DataFusion 55.1 capsule API."""


class SedonaExtension:
    def manifest(self):
        # Keep validation possible before importing any native capsule provider.
        return {
            "name": "sedona",
            "version": "0.1.0",
            "api_version": 1,
            "datafusion_version": "55.1.0",
            "arrow_version": "59.3.0",
            "placement": "any",
            "relation_types": [],
        }

    def bind(self, session_id):
        from ._native import BoundSedona

        return BoundSedona(session_id)


extension = SedonaExtension()
```

### Native package dependencies {#listing-sedona-cargo}

Source: [examples/extensions/sedona/Cargo.toml](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/examples/extensions/sedona/Cargo.toml). 34 lines.

```toml
[package]
name = "sail-sedona-extension"
version = "0.1.0"
edition = "2021"
publish = false
license = "Apache-2.0"

# This wheel is deliberately compiled independently of Sail.
[workspace]
exclude = [".deps/sedona-db", ".deps/sedona-db/*"]

[lib]
name = "_native"
crate-type = ["cdylib"]

[dependencies]
arrow-schema = "=59.3.0"
datafusion-common = { version = "=55.1.0", default-features = false }
datafusion-expr = { version = "=55.1.0", default-features = false }
datafusion-ffi = "=55.1.0"
pyo3 = "=0.29.0"
sedona-common = { path = ".deps/sedona-db/rust/sedona-common" }
sedona-expr = { path = ".deps/sedona-db/rust/sedona-expr" }
sedona-functions = { path = ".deps/sedona-db/rust/sedona-functions" }
sedona-geos = { path = ".deps/sedona-db/c/sedona-geos" }
sedona-schema = { path = ".deps/sedona-db/rust/sedona-schema" }

[profile.dev]
debug = 0
incremental = false

[profile.release]
debug = 0
incremental = false
```

### Python packaging and entry point {#listing-sedona-pyproject}

Source: [examples/extensions/sedona/pyproject.toml](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/examples/extensions/sedona/pyproject.toml). 19 lines.

```toml
[build-system]
requires = ["maturin>=1.8,<2"]
build-backend = "maturin"

[project]
name = "sail-sedona-extension"
version = "0.1.0"
description = "Apache SedonaDB native scalar extension for the Sail extension proof of concept"
requires-python = ">=3.12"
license = "Apache-2.0"
license-files = ["LICENSE-SEDONADB", "NOTICE-SEDONADB", "LICENSE-GEOS", "NOTICE"]

[project.entry-points."pysail.extensions"]
sedona = "sail_sedona:extension"

[tool.maturin]
features = ["pyo3/extension-module"]
module-name = "sail_sedona._native"
python-source = "python"
```

### Complete spatial SQL and shuffle client {#listing-sedona-client}

Source: [examples/extensions/TUTORIAL.md](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/examples/extensions/TUTORIAL.md#L166-L185). 20 lines.

```python
from pyspark.sql.connect.session import SparkSession
from pyspark.sql import functions as F
spark = SparkSession.builder.remote("sc://127.0.0.1:50051").create()
try:
    row = spark.sql("""SELECT
        ST_AsText(ST_Point(1.0, 2.0)) AS wkt,
        ST_Distance(ST_Point(0.0, 0.0), ST_Point(3.0, 4.0)) AS distance
    """).first()
    print(row)
    assert row.distance == 5.0
    points = spark.range(0, 17, numPartitions=4).selectExpr(
        "id", "ST_Point(CAST(id AS DOUBLE), 2.0) AS geom")
    rows = points.repartition(4, "id").selectExpr(
        "id", "ST_AsText(geom) AS wkt",
        "ST_Distance(geom, ST_Point(0.0, 2.0)) AS distance"
    ).orderBy("id").collect()
    assert [r.distance for r in rows] == [float(i) for i in range(17)]
    print("Sedona: 17 geometry rows survived the shuffle")
finally:
    spark.stop()
```

### Complete native adapter tests {#listing-sedona-tests}

Source: [examples/extensions/sedona/src/tests.rs](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/examples/extensions/sedona/src/tests.rs). 178 lines.

```rust
use arrow_schema::{Field, FieldRef};
use datafusion_expr::{ReturnFieldArgs, ScalarFunctionArgs, ScalarUDFImpl};
use datafusion_ffi::udf::ForeignScalarUDF;

use super::*;

#[test]
fn kernel_panic_becomes_a_result_before_the_ffi_boundary() {
    let result: Result<()> = guarded(|| panic!("injected native kernel failure"));
    assert!(result
        .unwrap_err()
        .to_string()
        .contains("native scalar panicked"));
}

fn argument(value: ScalarValue) -> (ColumnarValue, FieldRef) {
    let field = Arc::new(Field::new("arg", value.data_type(), true));
    (ColumnarValue::Scalar(value), field)
}

fn one_value(value: ColumnarValue) -> ScalarValue {
    // The Arrow FFI materializes scalar arguments as one-row arrays. Assert
    // cardinality explicitly, then compare the exact value rather than the
    // implementation's Scalar/Array representation.
    let array = value.into_array(1).unwrap();
    assert_eq!(array.len(), 1);
    ScalarValue::try_from_array(&array, 0).unwrap()
}

fn call(
    bound: &BoundSedona,
    name: &str,
    args: Vec<(ColumnarValue, FieldRef)>,
) -> Result<(ColumnarValue, FieldRef)> {
    let function = bound
        .functions
        .iter()
        .find(|f| f.inner.name() == name)
        .unwrap();
    // A foreign marker prevents the same-library optimization bypassing FFI.
    extern "C" fn foreign_marker() -> usize {
        0
    }
    let mut ffi = FFI_ScalarUDF::from(Arc::clone(&function.inner));
    ffi.library_marker_id = foreign_marker;
    let imported: Arc<dyn ScalarUDFImpl> = ffi.into();
    assert!(imported.is::<ForeignScalarUDF>());
    let function = ScalarUDF::new_from_shared_impl(imported);
    let (values, fields): (Vec<_>, Vec<_>) = args.into_iter().unzip();
    let rows = values
        .iter()
        .filter_map(|value| match value {
            ColumnarValue::Array(array) => Some(array.len()),
            ColumnarValue::Scalar(_) => None,
        })
        .next()
        .unwrap_or(1);
    let scalars = values
        .iter()
        .map(|v| match v {
            ColumnarValue::Scalar(s) => Some(s),
            ColumnarValue::Array(_) => None,
        })
        .collect::<Vec<_>>();
    let result_field = function.return_field_from_args(ReturnFieldArgs {
        arg_fields: &fields,
        scalar_arguments: &scalars,
    })?;
    let value = function.invoke_with_args(ScalarFunctionArgs {
        args: values,
        arg_fields: fields,
        number_rows: rows,
        return_field: Arc::clone(&result_field),
        config_options: Arc::new(ConfigOptions::new()),
    })?;
    Ok((value, result_field))
}

#[test]
fn ffi_geometry_metadata_and_geos_predicate() {
    let bound = BoundSedona::new("ffi-test".to_string()).unwrap();
    let point = call(
        &bound,
        "st_point",
        vec![
            argument(ScalarValue::Float64(Some(1.0))),
            argument(ScalarValue::Float64(Some(2.0))),
        ],
    )
    .unwrap();
    let polygon = call(
        &bound,
        "st_geomfromwkt",
        vec![argument(ScalarValue::Utf8(Some(
            "POLYGON ((0 0, 3 0, 3 3, 0 3, 0 0))".to_string(),
        )))],
    )
    .unwrap();
    let result = call(&bound, "st_intersects", vec![point.clone(), polygon]).unwrap();
    assert_eq!(one_value(result.0), ScalarValue::Boolean(Some(true)));
    let result = call(&bound, "st_astext", vec![point]).unwrap();
    assert_eq!(
        one_value(result.0),
        ScalarValue::Utf8(Some("POINT(1 2)".into()))
    );
}

#[test]
fn ffi_null_geometry_and_aliases_are_preserved() {
    let bound = BoundSedona::new("null-test".to_string()).unwrap();
    let null = call(
        &bound,
        "st_geomfromwkt",
        vec![argument(ScalarValue::Utf8(None))],
    )
    .unwrap();
    let result = call(&bound, "st_astext", vec![null]).unwrap();
    assert_eq!(one_value(result.0), ScalarValue::Utf8(None));
    let from_wkt = bound
        .functions
        .iter()
        .find(|f| f.inner.name() == "st_geomfromwkt")
        .unwrap();
    assert!(from_wkt.aliases().iter().any(|a| a == "st_geomfromtext"));
}

#[test]
fn envelope_bypass_state_matches_partial_update_for_nulls_and_filters() {
    use datafusion_common::arrow::array::{BooleanArray, StringArray};
    use datafusion_expr::EmitTo;

    let bound = BoundSedona::new("aggregate-port".to_string()).unwrap();
    let texts = ColumnarValue::Array(Arc::new(StringArray::from(vec![
        Some("POINT(1 2)"),
        None,
        Some("POINT(10 20)"),
        Some("POINT(3 4)"),
    ])));
    let geometry = call(
        &bound,
        "st_geomfromwkt",
        vec![(
            texts,
            Arc::new(Field::new("wkt", arrow_schema::DataType::Utf8, true)),
        )],
    )
    .unwrap();
    let input_type = SedonaType::from_storage_field(&geometry.1).unwrap();
    let args = [input_type];
    let functions = sedona_functions::register::default_function_set();
    let udf = functions.aggregate_udf("st_envelope_agg").unwrap();
    let (kernel, output_type) = udf
        .kernels()
        .iter()
        .find_map(|kernel| {
            kernel
                .return_type(&args)
                .unwrap()
                .map(|output| (kernel, output))
        })
        .unwrap();
    let arrays = [geometry.0.into_array(4).unwrap()];
    let groups = [0, 0, 1, 1];
    let filter = BooleanArray::from(vec![Some(true), Some(true), Some(false), Some(true)]);
    let mut partial = kernel.groups_accumulator(&args, &output_type).unwrap();
    partial
        .update_batch(&arrays, &groups, Some(&filter), 3)
        .unwrap();
    let expected = partial.evaluate(EmitTo::All).unwrap();

    let bypass = kernel.groups_accumulator(&args, &output_type).unwrap();
    let states = bypass.convert_to_state(&arrays, Some(&filter)).unwrap();
    let mut merged = kernel.groups_accumulator(&args, &output_type).unwrap();
    merged.merge_batch(&states, &groups, 3).unwrap();
    let actual = merged.evaluate(EmitTo::All).unwrap();
    assert_eq!(actual.len(), 3);
    assert_eq!(actual.to_data(), expected.to_data());
}
```

### Installed-wheel smoke check {#listing-sedona-smoke}

Source: [examples/extensions/sedona/scripts/smoke.py](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/examples/extensions/sedona/scripts/smoke.py). 31 lines.

```python
"""Verify the installed wheel manifest and every native capsule without Sail."""

import ctypes
from importlib.metadata import entry_points

from sail_sedona import extension

manifest = extension.manifest()
assert manifest == {
    "name": "sedona",
    "version": "0.1.0",
    "api_version": 1,
    "datafusion_version": "55.1.0",
    "arrow_version": "59.3.0",
    "placement": "any",
    "relation_types": [],
}
entries = [e for e in entry_points(group="pysail.extensions") if e.name == "sedona"]
assert len(entries) == 1
assert entries[0].load().manifest() == manifest
bound = extension.bind("sedona-wheel-smoke")
functions = {f.name(): f for f in bound.scalar_udfs()}
assert len(functions) == 128
assert {"st_point", "st_geomfromwkt", "st_astext", "st_intersects", "st_distance"} <= functions.keys()
assert "st_geomfromtext" in functions["st_geomfromwkt"].aliases()
assert not {"st_asbinary", "st_geomfromwkb", "st_geogfromwkb", "st_setsrid", "st_srid"} & functions.keys()
is_valid = ctypes.pythonapi.PyCapsule_IsValid
is_valid.argtypes = [ctypes.py_object, ctypes.c_char_p]
is_valid.restype = ctypes.c_int
assert all(is_valid(f.__datafusion_scalar_udf__(), b"datafusion_scalar_udf") for f in functions.values())
print({"manifest": manifest, "scalars": len(functions), "capsules": "valid"})
```

### Pinned dependency preparation {#listing-sedona-prepare}

Source: [examples/extensions/sedona/scripts/prepare.py](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/examples/extensions/sedona/scripts/prepare.py). 57 lines.

```python
#!/usr/bin/env python3
"""Fetch a fixed Apache SedonaDB revision and apply the reviewed DF55 port."""

from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / ".deps" / "sedona-db"
REVISION = "0a1993d9be8bcf52150593ad08fc6a3412d50f29"
PATCH = ROOT / "patches" / "datafusion-55.patch"


def git(*args):
    return subprocess.run(["git", "-C", str(SOURCE), *args], check=True)


if not SOURCE.exists():
    SOURCE.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", "--filter=blob:none", "--no-checkout",
         "https://github.com/apache/sedona-db.git", str(SOURCE)],
        check=True,
    )
    git("checkout", "--detach", REVISION)
else:
    actual = subprocess.check_output(
        ["git", "-C", str(SOURCE), "rev-parse", "HEAD"], text=True
    ).strip()
    if actual != REVISION:
        raise SystemExit(f"Expected Apache SedonaDB {REVISION}, found {actual}")

applied = subprocess.run(
    ["git", "-C", str(SOURCE), "apply", "--reverse", "--check", str(PATCH)],
    capture_output=True,
).returncode == 0
if not applied:
    git("apply", "--check", str(PATCH))
    git("apply", str(PATCH))

# A reversible patch alone does not prove that unrelated source was unchanged.
# Construct the expected patched tree with an isolated index, without resetting
# the checkout or touching its own index, and compare every tracked source file.
with tempfile.TemporaryDirectory(prefix="sail-sedona-source-") as temporary:
    env = dict(os.environ, GIT_INDEX_FILE=str(Path(temporary) / "index"))
    command = ["git", "-C", str(SOURCE)]
    subprocess.run(command + ["read-tree", REVISION], env=env, check=True)
    subprocess.run(command + ["apply", "--cached", str(PATCH)], env=env, check=True)
    expected = subprocess.check_output(command + ["write-tree"], env=env, text=True).strip()
    subprocess.run(command + ["diff", "--exit-code", expected, "--"], check=True)
    extras = subprocess.check_output(
        command + ["ls-files", "--others", "--exclude-standard"], text=True
    ).strip()
    if extras:
        raise SystemExit(f"Unexpected untracked files in pinned SedonaDB source:\n{extras}")
print(f"Apache SedonaDB {REVISION}, DF55 patch ready at {SOURCE}")
```

### Complete SedonaDB compatibility patch {#listing-sedona-patch}

Source: [examples/extensions/sedona/patches/datafusion-55.patch](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/examples/extensions/sedona/patches/datafusion-55.patch). 111 lines.

```diff
diff --git a/Cargo.toml b/Cargo.toml
index 4f7c991..4d01e6a 100644
--- a/Cargo.toml
+++ b/Cargo.toml
@@ -71,14 +71,14 @@ categories = ["science::geo", "database"]
 adbc_core = ">=0.24.0"
 adbc_ffi = ">=0.24.0"
 approx = "0.5"
-arrow = { version = "58.3.0", features = ["prettyprint", "ffi", "chrono-tz"] }
-arrow-array = { version = "58.3.0" }
-arrow-buffer = { version = "58.3.0" }
-arrow-cast = { version = "58.3.0" }
-arrow-data = { version = "58.3.0" }
-arrow-ipc = { version = "58.3.0" }
-arrow-json = { version = "58.3.0" }
-arrow-schema = { version = "58.3.0" }
+arrow = { version = "=59.3.0", features = ["prettyprint", "ffi", "chrono-tz"] }
+arrow-array = { version = "=59.3.0" }
+arrow-buffer = { version = "=59.3.0" }
+arrow-cast = { version = "=59.3.0" }
+arrow-data = { version = "=59.3.0" }
+arrow-ipc = { version = "=59.3.0" }
+arrow-json = { version = "=59.3.0" }
+arrow-schema = { version = "=59.3.0" }
 async-trait = { version = "0.1.87" }
 bytemuck = "1.25"
 byteorder = "1"
@@ -86,21 +86,21 @@ bytes = "1.11"
 chrono = { version = "0.4.41", default-features = false }
 comfy-table = { version = "8.0" }
 criterion = { version = "0.8", features = ["html_reports"] }
-datafusion = { version = "54.1.0", default-features = false }
-datafusion-catalog = { version = "54.1.0" }
-datafusion-common = { version = "54.1.0", default-features = false }
-datafusion-common-runtime = { version = "54.1.0", default-features = false }
-datafusion-proto = { version = "54.1.0", default-features = false }
-datafusion-datasource = { version = "54.1.0", default-features = false }
-datafusion-datasource-parquet = { version = "54.1.0" }
-datafusion-execution = { version = "54.1.0", default-features = false }
-datafusion-expr = { version = "54.1.0", default-features = false }
-datafusion-ffi = {  version = "54.1.0" }
-datafusion-optimizer = { version = "54.1.0" }
-datafusion-physical-expr = { version = "54.1.0" }
-datafusion-physical-plan = { version = "54.1.0" }
-datafusion-pruning = { version = "54.1.0" }
-datafusion-session = { version = "54.1.0" }
+datafusion = { version = "=55.1.0", default-features = false }
+datafusion-catalog = { version = "=55.1.0" }
+datafusion-common = { version = "=55.1.0", default-features = false }
+datafusion-common-runtime = { version = "=55.1.0", default-features = false }
+datafusion-proto = { version = "=55.1.0", default-features = false }
+datafusion-datasource = { version = "=55.1.0", default-features = false }
+datafusion-datasource-parquet = { version = "=55.1.0" }
+datafusion-execution = { version = "=55.1.0", default-features = false }
+datafusion-expr = { version = "=55.1.0", default-features = false }
+datafusion-ffi = {  version = "=55.1.0" }
+datafusion-optimizer = { version = "=55.1.0" }
+datafusion-physical-expr = { version = "=55.1.0" }
+datafusion-physical-plan = { version = "=55.1.0" }
+datafusion-pruning = { version = "=55.1.0" }
+datafusion-session = { version = "=55.1.0" }
 dirs = "7.0.0"
 env_logger = "0.11"
 fastrand = "2.4"
@@ -122,8 +122,8 @@ num-traits = { version = "0.2", default-features = false, features = ["libm"] }
 object_store = { version = "0.13.2", default-features = false }
 once_cell = "1.20"
 parking_lot = "0.12"
-parquet = { version = "58.3.0", default-features = false, features = ["arrow", "async", "geospatial", "object_store"] }
-parquet-geospatial = { version = "58.3.0" }
+parquet = { version = "=59.3.0", default-features = false, features = ["arrow", "async", "geospatial", "object_store"] }
+parquet-geospatial = { version = "=59.3.0" }
 pin-project-lite = "0.2"
 prost = "0.14.1"
 pyo3 = { version = "0.29.0" }
diff --git a/rust/sedona-functions/src/st_envelope_agg.rs b/rust/sedona-functions/src/st_envelope_agg.rs
index 1b5f9ec..b4bc203 100644
--- a/rust/sedona-functions/src/st_envelope_agg.rs
+++ b/rust/sedona-functions/src/st_envelope_agg.rs
@@ -442,10 +442,29 @@ impl<T: WkbBounder2D + Default + 'static> GroupsAccumulator for BoundsGroupsAccu
         &mut self,
         values: &[ArrayRef],
         group_indices: &[usize],
-        opt_filter: Option<&arrow_array::BooleanArray>,
         total_num_groups: usize,
     ) -> Result<()> {
-        self.merge_state(values, group_indices, opt_filter, total_num_groups)
+        self.merge_state(values, group_indices, None, total_num_groups)
+    }
+
+    fn convert_to_state(
+        &self,
+        values: &[ArrayRef],
+        opt_filter: Option<&BooleanArray>,
+    ) -> Result<Vec<ArrayRef>> {
+        // The bypass path represents every input row as its own group, while
+        // preserving the normal update path's null and FILTER semantics.
+        let rows = values[0].len();
+        let groups: Vec<_> = (0..rows).collect();
+        let mut accumulator = Self::new(self.input_type.clone());
+        accumulator.execute_update(
+            values,
+            &groups,
+            opt_filter,
+            rows,
+            self.input_type.clone(),
+        )?;
+        accumulator.emit_state(EmitTo::All)
     }
 
     fn evaluate(&mut self, emit_to: EmitTo) -> Result<ArrayRef> {
```

### Original two-wheel build script {#listing-build-script}

Source: [examples/extensions/scripts/build.sh](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/examples/extensions/scripts/build.sh). 55 lines.

```bash
#!/usr/bin/env bash
# Reproducible local PoC: one host executable, two independent native wheels.
set -euo pipefail
repo=$(cd "$(dirname "$0")/../../.." && pwd)
base="$repo/examples/extensions"
venv=${SAIL_EXTENSION_VENV:-"$repo/.venv"}
target=${SAIL_EXTENSION_TARGET:-"$repo/target/extensions-poc"}
python=${SAIL_EXTENSION_PYTHON:-python3.12}
export CARGO_INCREMENTAL=0 CARGO_PROFILE_DEV_DEBUG=0
export CARGO_BUILD_JOBS=${CARGO_BUILD_JOBS:-4}
df -h "$repo"
if [[ ! -x "$venv/bin/python" ]]; then
    uv venv --python "$python" "$venv"
fi
uv pip sync --python "$venv/bin/python" "$base/requirements.lock"
export PYO3_PYTHON="$venv/bin/python"
if [[ "$(uname -s)" == Darwin ]]; then
    export DYLD_LIBRARY_PATH=$("$venv/bin/python" -c 'import sysconfig; print(sysconfig.get_config_var("LIBDIR"))')
else
    export LD_LIBRARY_PATH=$("$venv/bin/python" -c 'import sysconfig; print(sysconfig.get_config_var("LIBDIR"))')
fi
"$venv/bin/python" "$base/sedona/scripts/prepare.py"
mkdir -p "$target/wheels"
for package in sedona nutmeg; do
    raw=$(mktemp -d "$target/raw-wheel-$package.XXXXXX")
    CARGO_TARGET_DIR="$target/$package" "$venv/bin/python" -m maturin build \
        --manifest-path "$base/$package/Cargo.toml" --locked --profile dev \
        --interpreter "$venv/bin/python" --out "$raw" --auditwheel repair
    if [[ "$(uname -s)" == Darwin ]]; then
        "$venv/bin/python" -m delocate.cmd.delocate_wheel -v -w "$raw/repaired" "$raw"/*.whl
        raw="$raw/repaired"
    fi
    for wheel in "$raw"/*.whl; do
        if [[ "$package" == sedona ]]; then
            "$venv/bin/python" "$base/scripts/check_wheel.py" "$wheel" \
                --output "$target/sedona-native-dependencies.json"
        fi
        # A repaired macOS wheel may acquire a newer minimum OS tag. Remove
        # stale variants of this package so pip cannot pick the unrepaired one.
        "$venv/bin/python" - "$wheel" "$target/wheels" <<'PY'
from pathlib import Path
import shutil
import sys
wheel, output = map(Path, sys.argv[1:])
for old in output.glob(wheel.name.split('-')[0] + '-*.whl'):
    old.unlink()
shutil.copy2(wheel, output / wheel.name)
PY
    done
done
uv pip install --python "$venv/bin/python" --reinstall "$target"/wheels/*.whl
# Pecan keeps its established source directory; its distribution is pyspark-pecan.
uv pip install --python "$venv/bin/python" --no-deps "$base/graph-algorithms"
CARGO_TARGET_DIR="$target/host" cargo build --manifest-path "$repo/Cargo.toml" --locked -p sail-cli
printf 'Host: %s\nPython: %s\nWheels: %s\n' "$target/host/debug/sail" "$venv/bin/python" "$target/wheels"
```

### Native wheel dependency check {#listing-wheel-check}

Source: [examples/extensions/scripts/check\_wheel.py](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/examples/extensions/scripts/check_wheel.py). 65 lines.

```python
#!/usr/bin/env python3
"""Require the Sedona wheel's GEOS dependencies to resolve inside the wheel."""
import argparse
import json
from pathlib import Path
import platform
import subprocess
import tempfile
import zipfile


def check(wheel):
    with tempfile.TemporaryDirectory(prefix="sail-wheel-check-") as temporary:
        root = Path(temporary).resolve()
        with zipfile.ZipFile(wheel) as archive:
            archive.extractall(root)
        libraries = [path for path in root.rglob("*") if path.is_file() and
                     (path.name.endswith((".so", ".dylib")) or ".so." in path.name)]
        geos = [path for path in libraries if "geos" in path.name.lower()]
        if len(geos) < 2:
            raise RuntimeError("Sedona wheel must contain both GEOS C and C++ shared libraries")
        links = {}
        for library in libraries:
            if platform.system() == "Darwin":
                output = subprocess.check_output(["otool", "-L", str(library)], text=True)
                dependencies = [line.strip().split(" (", 1)[0] for line in output.splitlines()[1:]]
                # A dylib's own install ID appears in -L output but is not a dependency.
                ids = subprocess.check_output(["otool", "-D", str(library)], text=True).splitlines()[1:]
                dependencies = [name for name in dependencies if name not in ids]
                for name in dependencies:
                    if name.startswith(("/usr/lib/", "/System/Library/")):
                        continue
                    if not name.startswith("@loader_path/"):
                        raise RuntimeError(f"external native dependency in {library.name}: {name}")
                    resolved = (library.parent / name.removeprefix("@loader_path/")).resolve()
                    if not resolved.is_relative_to(root) or not resolved.is_file():
                        raise RuntimeError(f"unresolved bundled dependency: {name}")
            elif platform.system() == "Linux":
                output = subprocess.check_output(["patchelf", "--print-needed", str(library)], text=True)
                dependencies = output.splitlines()
                bundled = {path.name for path in libraries}
                for name in dependencies:
                    if "geos" in name.lower() and name not in bundled:
                        raise RuntimeError(f"external GEOS dependency in {library.name}: {name}")
                if library.name.startswith("_native"):
                    rpath = subprocess.check_output(["patchelf", "--print-rpath", str(library)], text=True)
                    if "$ORIGIN" not in rpath:
                        raise RuntimeError("native module lacks a wheel-relative library search path")
            else:
                raise RuntimeError("wheel dependency check supports macOS and Linux")
            links[str(library.relative_to(root))] = dependencies
        return {"wheel": wheel.name, "bundled_geos": [str(path.relative_to(root)) for path in geos],
                "dependencies": links}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = json.dumps(check(args.wheel), indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result)
    print(result, end="")
```

### Python dependency lock {#listing-requirements}

Source: [examples/extensions/requirements.lock](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/examples/extensions/requirements.lock). 69 lines.

```text
# This file was autogenerated by uv via the following command:
#    uv pip compile --universal --python .venv/bin/python examples/extensions/requirements.in -o examples/extensions/requirements.lock
altgraph==0.17.5 ; sys_platform == 'darwin'
    # via macholib
apache-sedona==1.8.0
    # via -r examples/extensions/requirements.in
attrs==26.1.0
    # via apache-sedona
colorama==0.4.6 ; sys_platform == 'win32'
    # via pytest
delocate==0.13.0 ; sys_platform == 'darwin'
    # via -r examples/extensions/requirements.in
googleapis-common-protos==1.75.4
    # via
    #   grpcio-status
    #   pyspark
grpcio==1.84.0
    # via
    #   grpcio-status
    #   pyspark
grpcio-status==1.84.0
    # via pyspark
iniconfig==2.3.0
    # via pytest
macholib==1.16.4 ; sys_platform == 'darwin'
    # via delocate
maturin==1.9.6
    # via -r examples/extensions/requirements.in
numpy==2.5.3
    # via
    #   pandas
    #   pyspark
    #   shapely
packaging==26.3
    # via
    #   delocate
    #   pytest
pandas==3.0.6
    # via pyspark
pluggy==1.6.0
    # via pytest
protobuf==7.36.2
    # via
    #   googleapis-common-protos
    #   grpcio-status
py4j==0.10.9.9
    # via pyspark
pyarrow==21.0.0
    # via
    #   -r examples/extensions/requirements.in
    #   pyspark
pygments==2.21.0
    # via pytest
pyspark==4.0.1
    # via -r examples/extensions/requirements.in
pytest==8.4.2
    # via -r examples/extensions/requirements.in
python-dateutil==2.9.0.post0
    # via pandas
shapely==2.1.2
    # via apache-sedona
six==1.17.0
    # via python-dateutil
typing-extensions==4.16.0
    # via
    #   delocate
    #   grpcio
tzdata==2026.4 ; sys_platform == 'emscripten' or sys_platform == 'win32'
    # via pandas
```

### Complete relation envelope {#listing-protocol}

Source: [crates/sail-spark-connect/proto/sail/extension/v1/extension.proto](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/crates/sail-spark-connect/proto/sail/extension/v1/extension.proto). 20 lines.

```protobuf
// Experimental local-mode protocol. This schema is a wire contract, not a native ABI.
syntax = "proto3";
package sail.extension.v1;

import "spark/connect/base.proto";
import "spark/connect/expressions.proto";

// Pack into Relation.extension with type URL:
// type.googleapis.com/sail.extension.v1.SailExtensionRequest
message SailExtensionRequest {
  string payload_type_url = 1;
  bytes payload = 2;
  // Only Plan.root is accepted. Names are restored to the input DataFrame's
  // user-facing names before the native handler receives a physical plan.
  repeated spark.connect.Plan inputs = 3;
  // Reserved by the proposal; this PoC rejects any occurrence of this field.
  repeated spark.connect.Expression input_expressions = 4;
  // Required value: 1. An omitted proto3 value (0) is rejected.
  uint32 envelope_version = 5;
}
```

### Complete optional resource ABI {#listing-resource-abi}

Source: [crates/sail-native-resource-ffi/src/lib.rs](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/crates/sail-native-resource-ffi/src/lib.rs). 160 lines.

```rust
//! The small C ABI shared by independently compiled native extensions and Sail.
//! An opaque, prepaid memory lease crosses the boundary; Rust ownership and
//! allocator layouts stay entirely inside the library that issued the lease.
use std::ffi::{CStr, c_void};
use std::fmt::{Debug, Formatter};
use std::ptr::NonNull;
use std::sync::Arc;

pub const MEMORY_LEASE_CAPSULE: &CStr = c"sail_native_memory_lease_v1";

#[repr(C)]
struct Header {
    version: u32,
    size: u32,
}

/// A non-spillable host admission retained until the final clone is released.
///
/// Callbacks must be thread-safe and must never unwind. Every instance owns one
/// reference. A consumer may inspect the header before touching versioned fields.
#[repr(C)]
pub struct MemoryLease {
    header: Header,
    bytes: u64,
    opaque: *const c_void,
    retain: unsafe extern "C" fn(*const c_void),
    release: unsafe extern "C" fn(*const c_void),
}

// SAFETY: constructors require a Send + Sync owner; imports promise the same
// thread-safe callback contract. The opaque object is never accessed here.
unsafe impl Send for MemoryLease {}
unsafe impl Sync for MemoryLease {}

impl MemoryLease {
    /// Export ownership through callbacks compiled in the issuing library.
    pub fn new<T: Send + Sync + 'static>(owner: Arc<T>, bytes: u64) -> Self {
        unsafe extern "C" fn retain<T>(opaque: *const c_void) {
            // SAFETY: only new() constructs this token, from Arc<T>::into_raw.
            unsafe { Arc::<T>::increment_strong_count(opaque.cast::<T>()) };
        }
        unsafe extern "C" fn release<T>(opaque: *const c_void) {
            // SAFETY: each token owns one reference created by new()/retain().
            unsafe { drop(Arc::<T>::from_raw(opaque.cast::<T>())) };
        }
        Self {
            header: Header {
                version: 1,
                size: std::mem::size_of::<Self>() as u32,
            },
            bytes,
            opaque: Arc::into_raw(owner).cast::<c_void>(),
            retain: retain::<T>,
            release: release::<T>,
        }
    }

    /// Validate the ABI and quota, then take an independently releasable reference.
    ///
    /// # Safety
    /// `pointer` must address a readable, aligned header. A matching header must
    /// address a live MemoryLease with valid thread-safe, non-unwinding callbacks.
    /// Its issuing library must remain loaded until every imported clone is gone.
    pub unsafe fn import(
        pointer: NonNull<c_void>,
        expected_bytes: u64,
    ) -> Result<Self, &'static str> {
        // SAFETY: the caller guarantees at least the fixed header is readable.
        let header = unsafe { pointer.cast::<Header>().as_ref() };
        if header.version != 1 || header.size as usize != std::mem::size_of::<Self>() {
            return Err("native memory lease ABI mismatch");
        }
        // SAFETY: the validated header and caller's capsule contract cover Self.
        let lease = unsafe { pointer.cast::<Self>().as_ref() };
        if lease.bytes != expected_bytes || lease.opaque.is_null() {
            return Err("native memory lease quota mismatch");
        }
        Ok(lease.clone())
    }

    pub fn bytes(&self) -> u64 {
        self.bytes
    }
}

impl Clone for MemoryLease {
    fn clone(&self) -> Self {
        // SAFETY: self owns a live reference and callbacks obey the ABI contract.
        unsafe { (self.retain)(self.opaque) };
        Self {
            header: Header {
                version: self.header.version,
                size: self.header.size,
            },
            bytes: self.bytes,
            opaque: self.opaque,
            retain: self.retain,
            release: self.release,
        }
    }
}

impl Drop for MemoryLease {
    fn drop(&mut self) {
        // SAFETY: this instance owns exactly one reference, relinquished once.
        unsafe { (self.release)(self.opaque) };
    }
}

impl Debug for MemoryLease {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("MemoryLease")
            .field("version", &self.header.version)
            .field("bytes", &self.bytes)
            .finish_non_exhaustive()
    }
}

#[cfg(test)]
mod tests {
    use std::sync::atomic::{AtomicUsize, Ordering};

    use super::*;

    struct Owner(Arc<AtomicUsize>);
    impl Drop for Owner {
        fn drop(&mut self) {
            self.0.fetch_add(1, Ordering::SeqCst);
        }
    }

    #[test]
    fn imports_validate_before_clone_and_release_only_the_final_owner() -> Result<(), &'static str>
    {
        let drops = Arc::new(AtomicUsize::new(0));
        let exported = MemoryLease::new(Arc::new(Owner(drops.clone())), 64);
        let pointer = NonNull::from(&exported).cast::<c_void>();
        // SAFETY: the exported lease remains alive during both imports.
        assert!(unsafe { MemoryLease::import(pointer, 65) }.is_err());
        let imported = unsafe { MemoryLease::import(pointer, 64) }?;
        drop(exported);
        assert_eq!(drops.load(Ordering::SeqCst), 0);
        let output_owner = imported.clone();
        drop(imported);
        assert_eq!(drops.load(Ordering::SeqCst), 0);
        std::thread::spawn(move || drop(output_owner))
            .join()
            .map_err(|_| "release thread failed")?;
        assert_eq!(drops.load(Ordering::SeqCst), 1);
        let wrong = Header {
            version: 2,
            size: 8,
        };
        // SAFETY: a rejected version only reads the fixed header.
        assert!(
            unsafe { MemoryLease::import(NonNull::from(&wrong).cast::<c_void>(), 64) }.is_err()
        );
        Ok(())
    }
}
```

### Resource ABI crate manifest {#listing-resource-cargo}

Source: [crates/sail-native-resource-ffi/Cargo.toml](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/crates/sail-native-resource-ffi/Cargo.toml). 9 lines.

```toml
[package]
name = "sail-native-resource-ffi"
version = "0.1.0"
edition = "2024"
license = "Apache-2.0"
publish = false

[lints]
workspace = true
```

### Complete local server startup commands {#listing-server-start}

Source: [examples/extensions/TUTORIAL.md](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/examples/extensions/TUTORIAL.md#L144-L153). 10 lines.

```bash
export PYTHONHOME="$(.venv/bin/python -c 'import sys; print(sys.base_prefix)')"
export PYTHONPATH="$(.venv/bin/python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
export DYLD_LIBRARY_PATH="$(.venv/bin/python -c 'import sysconfig; print(sysconfig.get_config_var("LIBDIR") or "")')"
export LD_LIBRARY_PATH="$DYLD_LIBRARY_PATH"
export SAIL_EXPERIMENTAL_EXTENSIONS=1
export SAIL_EXECUTION__DEFAULT_PARALLELISM=4
export SAIL_CLUSTER__WORKER_INITIAL_COUNT=2
export SAIL_CLUSTER__WORKER_MAX_COUNT=2
SAIL_MODE=local SAIL_EXPERIMENTAL_PROCESS_WORKERS=0 \
  target/extensions-poc/host/debug/sail spark server --ip 127.0.0.1 --port 50051
```


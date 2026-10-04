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

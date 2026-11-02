    pub fn analyze(
        python_version: &str,
        command: &[u8],
        eval_type: spec::PySparkUdfType,
        argument_types: &[DataType],
        argument_literals: &[Option<ScalarValue>],
        kwargs: &[Option<String>],
        argument_is_tables: &[bool],
        large_var_types: bool,
    ) -> PyUdfResult<DataType> {
        check_python_udf_version(python_version)?;
        let _ = eval_type; // eval_type is not needed for the analyze call itself

        Python::attach(|py| -> PyUdfResult<DataType> {
            // Load the UDTF handler by directly unpickling the command bytes.
            // The command is a CloudPickle-serialized UDTF class (compatible with pickle.loads).
            let cloudpickle = PyModule::import(py, intern!(py, "pyspark.cloudpickle"))
                .map_err(PyUdfError::PythonError)?;
            let handler = cloudpickle
                .getattr(intern!(py, "loads"))
                .map_err(PyUdfError::PythonError)?
                .call1((command,))
                .map_err(PyUdfError::PythonError)?;

            // Build the list of arguments: (arrow_type, is_constant, value_array, kwarg_name, is_table)
            let mut arguments: Vec<Bound<'_, PyAny>> = Vec::with_capacity(argument_types.len());
            for (i, dt) in argument_types.iter().enumerate() {
                let arrow_type = dt
                    .try_to_py(py, large_var_types)
                    .map_err(PyUdfError::PythonError)?;
                let (is_constant, value_array) = match argument_literals.get(i) {
                    Some(Some(sv)) => {
                        // Constant expression: create a single-element PyArrow array.
                        // The value may be null (sv.is_null()) in which case the Python value
                        // will be None, representing a null literal constant expression.
                        let array = sv
                            .to_array()
                            .map_err(|e| PyValueError::new_err(e.to_string()))
                            .map_err(PyUdfError::PythonError)?;
                        let pyarrow_array = array
                            .try_to_py(py, large_var_types)
                            .map_err(PyUdfError::PythonError)?;
                        (true, Some(pyarrow_array))
                    }
                    // None (out of bounds) or Some(None) (not a constant expression)
                    _ => (false, None),
                };
                let kwarg_name: Option<&str> = kwargs.get(i).and_then(|k| k.as_deref());
                let is_table = argument_is_tables.get(i).copied().unwrap_or(false);
                let tuple = (arrow_type, is_constant, value_array, kwarg_name, is_table)
                    .into_pyobject(py)
                    .map_err(PyUdfError::PythonError)?;
                arguments.push(tuple.into_any());
            }

            let py_arguments = arguments
                .into_pyobject(py)
                .map_err(PyUdfError::PythonError)?;

            // Import and call the analyze_udtf helper from spark.py.
            // Any Python exception raised by the UDTF's analyze() method is converted to an
            // AnalysisError so that it surfaces as an AnalysisException on the client side.
            use crate::python::spark::PySpark;
            let schema_pyarrow = PySpark::analyze_udtf(py, handler, py_arguments)
                .map_err(|e| PyUdfError::AnalysisError(e.to_string()))?;

            // Convert PyArrow schema back to Arrow schema
            let schema =
                Schema::from_pyarrow_bound(&schema_pyarrow).map_err(PyUdfError::PythonError)?;
            Ok(DataType::Struct(schema.fields().clone()))
        })
    }


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

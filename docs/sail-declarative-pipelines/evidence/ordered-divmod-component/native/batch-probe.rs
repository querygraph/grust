
#[derive(Debug, PartialEq, Eq, Hash)]
struct SelectedBatchProbe(SparkDivModLazy);

impl HigherOrderUDFImpl for SelectedBatchProbe {
    fn name(&self) -> &str { "selected_batch_probe" }
    fn signature(&self) -> &datafusion_expr::HigherOrderSignature { self.0.signature() }
    fn lambda_parameters(&self, step: usize, fields: &[ValueOrLambda<Arc<Field>, Option<Arc<Field>>>]) -> Result<datafusion_expr::LambdaParametersProgress> { self.0.lambda_parameters(step, fields) }
    fn return_field_from_args(&self, args: HigherOrderReturnFieldArgs) -> Result<Arc<Field>> { self.0.return_field_from_args(args) }
    fn coerce_value_types(&self, types: &[DataType]) -> Result<Vec<DataType>> { self.0.coerce_value_types(types) }
    fn short_circuits(&self) -> bool { true }
    fn invoke_with_args(&self, args: datafusion_expr::HigherOrderFunctionArgs) -> Result<ColumnarValue> {
        use datafusion::arrow::array::UInt64Array;
        use datafusion::arrow::compute::take;
        use crate::functions_nested_utils::{evaluate_lambda_rows, scatter_active_rows};
        use super::divisor::numeric_zero_mask;
        let [ValueOrLambda::Lambda(right), ValueOrLambda::Lambda(left), ValueOrLambda::Lambda(operation)] = args.args.as_slice() else { return Err(exec_datafusion_err!("probe lambda arguments")) };
        let rows=(0..args.number_rows as u64).collect::<Vec<_>>();
        let right_value=evaluate_lambda_rows(right, &rows)?;
        let zero=if self.0.ansi_mode() { None } else { Some(numeric_zero_mask(&right_value)?) };
        let mut active=rows.into_iter().filter(|&row| right_value.is_valid(row as usize) && zero.as_ref().is_none_or(|z| !z.value(row as usize))).collect::<Vec<_>>();
        if active.is_empty() { return Ok(ColumnarValue::Array(datafusion::arrow::array::new_null_array(args.return_type(),args.number_rows))) }
        let right_value=take(right_value.as_ref(),&UInt64Array::from(active.clone()),None)?;
        let left_value=evaluate_lambda_rows(left,&active)?;
        let keep=(0..active.len()).filter(|&i| left_value.is_valid(i)).map(|i| i as u64).collect::<Vec<_>>();
        active=keep.iter().map(|&i| active[i as usize]).collect();
        if active.is_empty() { return Ok(ColumnarValue::Array(datafusion::arrow::array::new_null_array(args.return_type(),args.number_rows))) }
        let indices=UInt64Array::from(keep);
        let left_value=take(left_value.as_ref(),&indices,None)?;
        let right_value=take(right_value.as_ref(),&indices,None)?;
        let left_arg=|| Ok(Arc::clone(&left_value));let right_arg=|| Ok(Arc::clone(&right_value));
        let indices=UInt64Array::from(active.clone());
        let value=operation.evaluate(&[&left_arg,&right_arg],|arrays| Ok(datafusion::arrow::compute::take_arrays(arrays,&indices,None)?))?.into_array(active.len())?;
        Ok(ColumnarValue::Array(scatter_active_rows(value,&active,args.number_rows)?))
    }
}

fn selected_batch_probe(mut expression: Expr) -> Expr {
    if let Expr::HigherOrderFunction(ref mut hof)=expression { hof.func=Arc::new(HigherOrderUDF::new_from_impl(SelectedBatchProbe(SparkDivModLazy::new(true)))) }
    expression
}

#[test]
fn selected_batch_error_and_cost_probe() -> Result<()> {
    use std::time::Instant;
    let input=batch(vec![Some(8),Some(9)],vec![Some(2),Some(3)])?;
    let trace=Trace::default();
    let expr=logical(observed_column("l",Arc::clone(&trace),Some(0)),observed_column("r",Arc::clone(&trace),Some(1)),observed_operation(Arc::clone(&trace)),true);
    let row=physical(&expr,input.schema().as_ref())?.evaluate(&input).err().ok_or_else(||exec_datafusion_err!("expected row error"))?;
    assert!(row.to_string().contains("l failed on row 0"));
    trace.lock().map_err(|_|exec_datafusion_err!("trace lock"))?.clear();
    let batch_error=physical(&selected_batch_probe(expr),input.schema().as_ref())?.evaluate(&input).err().ok_or_else(||exec_datafusion_err!("expected selected batch error"))?;
    assert!(batch_error.to_string().contains("r failed on row 1"));
    eprintln!("ERROR_SELECTION row={row}; selected_batch={batch_error}");
    let input=batch(vec![Some(8);1024],vec![Some(2);1024])?;
    let operation=variable("l",DataType::Int32,false)/variable("r",DataType::Int32,false);
    let row=logical(col("l"),col("r"),operation,true);
    let expressions=[col("l")/col("r"),row.clone(),selected_batch_probe(row)];
    let physicals=expressions.iter().map(|e|physical(e,input.schema().as_ref())).collect::<Result<Vec<_>>>()?;
    let expected=physicals[0].evaluate(&input)?.into_array(1024)?;
    for expression in &physicals { assert_eq!(expression.evaluate(&input)?.into_array(1024)?.as_ref(),expected.as_ref()); }
    let mut timings=vec![];
    for expression in physicals {
        for _ in 0..3 {std::hint::black_box(expression.evaluate(&input)?);}
        let start=Instant::now();
        for _ in 0..20 {std::hint::black_box(expression.evaluate(&input)?);}
        timings.push(start.elapsed().as_secs_f64());
    }
    eprintln!("COST_DIAGNOSTIC shared_host=true profile=unoptimized rows=1024 iterations=20 row_over_native={} selected_batch_over_native={}",timings[1]/timings[0],timings[2]/timings[0]);
    Ok(())
}

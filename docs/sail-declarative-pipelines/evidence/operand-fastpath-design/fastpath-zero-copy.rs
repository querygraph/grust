
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
        use datafusion::arrow::array::{NullArray, UInt64Array};
        use datafusion::arrow::compute::{take, take_arrays};
        use datafusion_expr::LambdaArgument;
        use crate::functions_nested_utils::scatter_active_rows;
        use super::divisor::numeric_zero_mask;
        fn evaluate(lambda:&LambdaArgument, rows:Option<&UInt64Array>, total:usize)->Result<ArrayRef> {
            let len=rows.map_or(total,Array::len);
            let dummy=||Ok(Arc::new(NullArray::new(len)) as ArrayRef);
            lambda.evaluate(&[&dummy],|arrays| match rows {
                Some(indices)=>Ok(take_arrays(arrays,indices,None)?),
                None=>Ok(arrays.to_vec()),
            })?.into_array(len)
        }
        let [ValueOrLambda::Lambda(right), ValueOrLambda::Lambda(left), ValueOrLambda::Lambda(operation)] = args.args.as_slice() else { return Err(exec_datafusion_err!("probe lambda arguments")) };
        let total=args.number_rows;
        if total==0 {return Ok(ColumnarValue::Array(datafusion::arrow::array::new_empty_array(args.return_type())))}
        let right_value=evaluate(right,None,total)?;
        if right_value.null_count()==total {return Ok(ColumnarValue::Array(datafusion::arrow::array::new_null_array(args.return_type(),total)))}
        let zeros=if self.0.ansi_mode() {None} else {Some(numeric_zero_mask(&right_value)?)};
        let mut rows=if right_value.null_count()==0 && zeros.as_ref().is_none_or(|z|z.true_count()==0) {None} else {
            Some(UInt64Array::from((0..total).filter(|&i|right_value.is_valid(i) && zeros.as_ref().is_none_or(|z|!z.value(i))).map(|i|i as u64).collect::<Vec<_>>()))
        };
        if rows.as_ref().is_some_and(|x|x.is_empty()) {return Ok(ColumnarValue::Array(datafusion::arrow::array::new_null_array(args.return_type(),total)))}
        let mut right_value=match rows.as_ref() {Some(indices)=>take(right_value.as_ref(),indices,None)?,None=>right_value};
        let mut left_value=evaluate(left,rows.as_ref(),total)?;
        if left_value.null_count()==left_value.len() {return Ok(ColumnarValue::Array(datafusion::arrow::array::new_null_array(args.return_type(),total)))}
        if left_value.null_count()!=0 {
            let keep=UInt64Array::from((0..left_value.len()).filter(|&i|left_value.is_valid(i)).map(|i|i as u64).collect::<Vec<_>>());
            left_value=take(left_value.as_ref(),&keep,None)?;
            right_value=take(right_value.as_ref(),&keep,None)?;
            rows=Some(match rows {
                None=>keep,
                Some(original)=>take(&original,&keep,None)?.as_any().downcast_ref::<UInt64Array>().ok_or_else(||exec_datafusion_err!("expected row indices"))?.clone(),
            });
        }
        let left_arg=||Ok(Arc::clone(&left_value));let right_arg=||Ok(Arc::clone(&right_value));
        let value=operation.evaluate(&[&left_arg,&right_arg],|arrays| match rows.as_ref() {
            Some(indices)=>Ok(take_arrays(arrays,indices,None)?),
            None=>Ok(arrays.to_vec()),
        })?.into_array(left_value.len())?;
        Ok(ColumnarValue::Array(match rows {
            Some(indices)=>scatter_active_rows(value,indices.values().as_ref(),total)?,
            None=>value,
        }))
    }
}

fn selected_batch_probe(mut expression: Expr) -> Expr {
    if let Expr::HigherOrderFunction(ref mut hof)=expression { hof.func=Arc::new(HigherOrderUDF::new_from_impl(SelectedBatchProbe(SparkDivModLazy::new(true)))) }
    expression
}

#[test]
fn optimized_zero_copy_error_and_cost_probe() -> Result<()> {
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
        for _ in 0..5 {std::hint::black_box(expression.evaluate(&input)?);}
        let mut samples=Vec::new();
        for _ in 0..5 {
            let start=Instant::now();
            for _ in 0..50 {std::hint::black_box(expression.evaluate(&input)?);}
            samples.push(start.elapsed().as_secs_f64());
        }
        samples.sort_by(f64::total_cmp);
        timings.push(samples[2]);
    }
    eprintln!("COST_DIAGNOSTIC all_active_no_take=true shared_host=true profile=release rows=1024 iterations=50 samples=5 statistic=median row_over_native={} selected_batch_over_native={}",timings[1]/timings[0],timings[2]/timings[0]);
    Ok(())
}

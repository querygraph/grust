use super::*;
use arrow::array::{Array, ArrayRef, BooleanArray, Float64Array, Int64Array, StructArray};
use datafusion_expr::EmitTo;

fn array(rows: &[(f64, i64, i64)]) -> ArrayRef {
    Arc::new(StructArray::from(vec![
        (
            Arc::new(Field::new("distance", DataType::Float64, false)),
            Arc::new(Float64Array::from_iter_values(rows.iter().map(|row| row.0))) as ArrayRef,
        ),
        (
            Arc::new(Field::new("hops", DataType::Int64, false)),
            Arc::new(Int64Array::from_iter_values(rows.iter().map(|row| row.1))) as ArrayRef,
        ),
        (
            Arc::new(Field::new("parent", DataType::Int64, false)),
            Arc::new(Int64Array::from_iter_values(rows.iter().map(|row| row.2))) as ArrayRef,
        ),
    ]))
}

fn update(
    acc: &mut dyn GroupsAccumulator,
    values: &ArrayRef,
    indices: &[usize],
    filter: &BooleanArray,
    groups: usize,
    method: Method,
) -> Result<()> {
    let arrays = [values.clone(), values.clone()];
    acc.update_batch(
        match method {
            Method::Native9fCompactMin => &arrays[..1],
            Method::PlannerOrderedMinBy => &arrays,
        },
        indices,
        Some(filter),
        groups,
    )
}

#[test]
fn complete_key_signed_parent_ties_and_order_invariance() -> Result<()> {
    let rows = [
        (2.0, 0, 9),
        (1.0, 3, i64::MAX),
        (1.0, 2, i64::MAX),
        (1.0, 2, i64::MIN),
        (-1.0, 0, 0),
        (0.0, 0, 0),
    ];
    let expected = array(&[(1.0, 2, i64::MIN), (-1.0, 0, 0)]);
    for method in [Method::Native9fCompactMin, Method::PlannerOrderedMinBy] {
        for reverse in [false, true] {
            let mut rows = rows.to_vec();
            let mut groups = vec![0, 0, 0, 0, 1, 1];
            if reverse {
                rows.reverse();
                groups.reverse();
            }
            let input = array(&rows);
            let mut acc = accumulator(input.data_type(), method)?;
            update(
                acc.as_mut(),
                &input,
                &groups,
                &BooleanArray::from(vec![true; 6]),
                2,
                method,
            )?;
            assert_eq!(acc.evaluate(EmitTo::All)?.as_ref(), expected.as_ref());
        }
    }
    Ok(())
}

#[test]
fn filtered_dangerous_value_and_partial_merge_remain_exact() -> Result<()> {
    let first = array(&[(2.0, 0, 1), (-99.0, 0, i64::MIN), (4.0, 2, -9)]);
    let second = array(&[(1.0, 3, -1), (4.0, 1, i64::MAX)]);
    let expected = array(&[(1.0, 3, -1), (4.0, 1, i64::MAX)]);
    for method in [Method::Native9fCompactMin, Method::PlannerOrderedMinBy] {
        let mut a = accumulator(first.data_type(), method)?;
        let mut b = accumulator(second.data_type(), method)?;
        update(
            a.as_mut(),
            &first,
            &[0, 0, 1],
            &BooleanArray::from(vec![true, false, true]),
            2,
            method,
        )?;
        update(
            b.as_mut(),
            &second,
            &[0, 1],
            &BooleanArray::from(vec![true; 2]),
            2,
            method,
        )?;
        let mut final_acc = accumulator(first.data_type(), method)?;
        final_acc.merge_batch(&a.state(EmitTo::All)?, &[0, 1], 2)?;
        final_acc.merge_batch(&b.state(EmitTo::All)?, &[0, 1], 2)?;
        assert_eq!(final_acc.evaluate(EmitTo::All)?.as_ref(), expected.as_ref());
    }
    Ok(())
}

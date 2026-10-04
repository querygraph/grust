//! Exact public DataFusion ordered LAST_VALUE, conditional on Sail's min_by rewrite.
//! No Sail plan was captured by this probe; this is not a whole-query measurement.
use arrow::array::{Array, ArrayRef, BooleanArray, Int64Array};
use arrow::compute::SortOptions;
use arrow::datatypes::{DataType, Field, Schema};
use datafusion_common::ScalarValue;
use datafusion_expr::function::AccumulatorArgs;
use datafusion_expr::{EmitTo, GroupsAccumulator};
use datafusion_functions_aggregate::first_last::last_value_udaf;
use datafusion_physical_expr::{PhysicalExpr, PhysicalSortExpr, expressions::Column};
use serde_json::json;
use std::sync::Arc;

mod meter;
use meter::Phase;
#[global_allocator]
static ALLOCATOR: meter::CountedSystem = meter::CountedSystem;
const BATCH: usize = 8192;

fn accumulator() -> Box<dyn GroupsAccumulator> {
    let field = Arc::new(Field::new("neighbor", DataType::Int64, true));
    let schema = Schema::new(vec![
        field.clone(),
        Arc::new(Field::new("priority", DataType::Int64, true)),
    ]);
    let expressions: Vec<Arc<dyn PhysicalExpr>> = vec![Arc::new(Column::new("neighbor", 0))];
    let order = [PhysicalSortExpr {
        expr: Arc::new(Column::new("priority", 1)),
        options: SortOptions {
            descending: true,
            nulls_first: true,
        },
    }];
    let fields = [field.clone()];
    let args = AccumulatorArgs {
        return_field: field,
        schema: &schema,
        ignore_nulls: false,
        order_bys: &order,
        is_reversed: false,
        name: "last_value_for_min_by",
        is_distinct: false,
        exprs: &expressions,
        expr_fields: &fields,
    };
    let udf = last_value_udaf();
    assert!(udf.groups_accumulator_supported(args.clone()));
    udf.create_groups_accumulator(args).unwrap()
}

struct Batch {
    arrays: Vec<ArrayRef>,
    indices: Vec<usize>,
    filter: BooleanArray,
    groups: usize,
}
fn batches(groups: usize, generation: i64) -> Vec<Batch> {
    (0..groups)
        .step_by(BATCH)
        .map(|start| {
            let end = (start + BATCH).min(groups);
            Batch {
                arrays: vec![
                    Arc::new(Int64Array::from_iter_values(
                        (start..end).map(|i| generation * 1_000_000 + i as i64),
                    )),
                    Arc::new(Int64Array::from_iter_values(
                        (start..end).map(|i| i as i64 - generation * 1_000_000),
                    )),
                ],
                indices: (start..end).collect(),
                filter: BooleanArray::from(vec![true; end - start]),
                groups: end,
            }
        })
        .collect()
}
fn update(acc: &mut dyn GroupsAccumulator, input: &[Batch], groups: usize, growing: bool) {
    for batch in input {
        acc.update_batch(
            &batch.arrays,
            &batch.indices,
            Some(&batch.filter),
            if growing { batch.groups } else { groups },
        )
        .unwrap();
    }
}
fn assert_values(array: &ArrayRef, start: usize, length: usize, generation: i64) {
    let actual = array.as_any().downcast_ref::<Int64Array>().unwrap();
    assert_eq!(actual.len(), length);
    assert_eq!(actual.null_count(), 0);
    for i in 0..length {
        assert_eq!(actual.value(i), generation * 1_000_000 + (start + i) as i64);
    }
}
fn bytes(arrays: &[ArrayRef]) -> usize {
    arrays.iter().map(|a| a.get_array_memory_size()).sum()
}

fn main() {
    let groups: usize = std::env::args().nth(1).unwrap().parse().unwrap();
    assert!([1000, 10_000, 100_000].contains(&groups));
    println!(
        "{}",
        json!({"groups":groups,"batch_rows":BATCH,
        "sizeof_scalar_value":size_of::<ScalarValue>(),"sizeof_inner_vec":size_of::<Vec<ScalarValue>>(),
        "boundary":"public DF55.1 ordered last_value(Int64 ORDER BY Int64 DESC NULLS FIRST), all-true nonnull-key filter; source-derived Sail rewrite, no captured Sail plan; requested System allocator bytes, not usable heap; exploratory shared laptop"})
    );
    let original = batches(groups, 0);
    let better = batches(groups, 1);
    let sparse = batches(groups.min(BATCH), 2);
    let source_scanned_first: usize = original.iter().map(|b| b.groups).sum();
    let dense_metadata = json!({"rows":groups,"batches":original.len(),"resident_groups_scanned_source_derived":source_scanned_first});
    let repeat_metadata = json!({"rows":groups,"batches":original.len(),"resident_groups_scanned_source_derived":groups*original.len()});
    let sparse_metadata = json!({"rows":groups.min(BATCH),"batches":1,"resident_groups_scanned_source_derived":groups});
    {
        let mut acc = accumulator();
        let phase = Phase::start();
        update(acc.as_mut(), &original, groups, true);
        phase.finish("first_update", acc.size(), 0, dense_metadata);
        let identical_metadata = repeat_metadata.clone();
        let phase = Phase::start();
        update(acc.as_mut(), &original, groups, false);
        phase.finish("repeat_identical", acc.size(), 0, identical_metadata);
        let phase = Phase::start();
        update(acc.as_mut(), &better, groups, false);
        phase.finish("repeat_improving", acc.size(), 0, repeat_metadata);
        let phase = Phase::start();
        update(acc.as_mut(), &sparse, groups, false);
        phase.finish("sparse_improving", acc.size(), 0, sparse_metadata);
        let metadata = json!({"emitted_groups":groups});
        let phase = Phase::start();
        let result = acc.evaluate(EmitTo::All).unwrap();
        phase.finish(
            "evaluate_all",
            acc.size(),
            result.get_array_memory_size(),
            metadata,
        );
        let actual = result.as_any().downcast_ref::<Int64Array>().unwrap();
        for i in 0..groups {
            assert_eq!(
                actual.value(i),
                if i < BATCH {
                    2_000_000 + i as i64
                } else {
                    1_000_000 + i as i64
                }
            );
        }
    }
    for emitted in [groups, 1, groups.min(BATCH)] {
        let mut acc = accumulator();
        update(acc.as_mut(), &original, groups, true);
        let metadata = json!({"emitted_groups":emitted,"remaining_groups":groups-emitted});
        let phase = Phase::start();
        let state = acc
            .state(if emitted == groups {
                EmitTo::All
            } else {
                EmitTo::First(emitted)
            })
            .unwrap();
        let capacity = state.capacity();
        phase.finish(
            if emitted == groups {
                "state_all"
            } else {
                "state_first"
            },
            acc.size(),
            bytes(&state),
            metadata,
        );
        println!(
            "{}",
            json!({"phase":"state_output_vec_capacity","emitted_groups":emitted,"remaining_groups":groups-emitted,
            "array_ref_vec_len":state.len(),"array_ref_vec_capacity":capacity,"sizeof_array_ref":size_of::<ArrayRef>()})
        );
        assert_eq!(state.len(), 3);
        assert_values(&state[0], 0, emitted, 0);
        assert_values(&state[1], 0, emitted, 0);
        let mut merged = accumulator();
        let indices: Vec<usize> = (0..emitted).collect();
        let metadata = json!({"rows":emitted});
        let phase = Phase::start();
        merged.merge_batch(&state, &indices, emitted).unwrap();
        phase.finish("merge_emitted_state", merged.size(), 0, metadata);
        assert_values(&merged.evaluate(EmitTo::All).unwrap(), 0, emitted, 0);
        if emitted < groups {
            assert_values(
                &acc.evaluate(EmitTo::All).unwrap(),
                emitted,
                groups - emitted,
                0,
            );
        }
    }
    println!("{}", json!({"checks":"passed","groups":groups}));
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn null_key_filter_values_ties_signed_extremes_and_state() {
        // Sail adds priority IS NOT NULL. NULL/false predicates also exclude rows.
        let values = Arc::new(Int64Array::from(vec![
            Some(7),
            Some(8),
            Some(9),
            None,
            Some(6),
            Some(5),
            Some(4),
            Some(3),
        ])) as ArrayRef;
        let keys = Arc::new(Int64Array::from(vec![
            Some(i64::MAX),
            Some(i64::MIN),
            Some(i64::MIN),
            Some(-1),
            None,
            Some(-2),
            Some(0),
            Some(0),
        ])) as ArrayRef;
        let filter = BooleanArray::from(vec![
            Some(true),
            Some(true),
            Some(true),
            Some(true),
            Some(false),
            Some(false),
            None,
            Some(true),
        ]);
        let mut acc = accumulator();
        acc.update_batch(&[values, keys], &[0, 0, 0, 1, 1, 1, 1, 2], Some(&filter), 4)
            .unwrap();
        let state = acc.state(EmitTo::First(2)).unwrap();
        let seen = state[2].as_any().downcast_ref::<BooleanArray>().unwrap();
        assert!(seen.value(0) && seen.value(1));
        let mut merged = accumulator();
        merged.merge_batch(&state, &[0, 1], 2).unwrap();
        assert_eq!(
            merged
                .evaluate(EmitTo::All)
                .unwrap()
                .as_any()
                .downcast_ref::<Int64Array>()
                .unwrap(),
            &Int64Array::from(vec![Some(8), None])
        );
        let rest = acc.state(EmitTo::All).unwrap();
        let seen = rest[2].as_any().downcast_ref::<BooleanArray>().unwrap();
        assert!(seen.value(0));
        assert!(!seen.value(1));
        assert_eq!(
            rest[0].as_any().downcast_ref::<Int64Array>().unwrap(),
            &Int64Array::from(vec![Some(3), None])
        );
    }

    #[test]
    fn repeat_and_later_batch_preserve_first_equal_key() {
        let mut acc = accumulator();
        let first = [
            Arc::new(Int64Array::from(vec![11, 12])) as ArrayRef,
            Arc::new(Int64Array::from(vec![3, -3])) as ArrayRef,
        ];
        acc.update_batch(&first, &[0, 1], None, 2).unwrap();
        let later = [
            Arc::new(Int64Array::from(vec![21, 22, 23])) as ArrayRef,
            Arc::new(Int64Array::from(vec![3, -4, 3])) as ArrayRef,
        ];
        acc.update_batch(&later, &[0, 1, 0], None, 2).unwrap();
        assert_eq!(
            acc.evaluate(EmitTo::All)
                .unwrap()
                .as_any()
                .downcast_ref::<Int64Array>()
                .unwrap(),
            &Int64Array::from(vec![11, 22])
        );
    }
}

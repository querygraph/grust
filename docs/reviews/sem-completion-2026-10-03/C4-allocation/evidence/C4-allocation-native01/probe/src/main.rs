//! Bounded same-payload/key allocation control; no graph or whole-query timing.
use arrow::array::{Array, ArrayRef, BooleanArray, Float64Array, Int64Array, StructArray};
use arrow::datatypes::{DataType, Field};
use current_struct_aggregate_allocation_probe::{Method, accumulator};
use datafusion_common::Result;
use datafusion_expr::{EmitTo, GroupsAccumulator};
use serde_json::json;
use std::sync::Arc;

mod meter;
#[global_allocator]
static ALLOCATOR: meter::CountedSystem = meter::CountedSystem;
const BATCH: usize = 8192;

struct Batch {
    value: ArrayRef,
    indices: Vec<usize>,
    filter: BooleanArray,
    growing_groups: usize,
}

fn input(groups: usize, distance: f64) -> ArrayRef {
    Arc::new(StructArray::from(vec![
        (
            Arc::new(Field::new("distance", DataType::Float64, false)),
            Arc::new(Float64Array::from(vec![distance; groups])) as ArrayRef,
        ),
        (
            Arc::new(Field::new("hops", DataType::Int64, false)),
            Arc::new(Int64Array::from(vec![2; groups])) as ArrayRef,
        ),
        (
            Arc::new(Field::new("parent", DataType::Int64, false)),
            Arc::new(Int64Array::from_iter_values(
                (0..groups).map(|i| i as i64 - groups as i64 / 2),
            )) as ArrayRef,
        ),
    ]))
}

fn batches(array: &ArrayRef) -> Vec<Batch> {
    (0..array.len())
        .step_by(BATCH)
        .map(|start| {
            let end = (start + BATCH).min(array.len());
            Batch {
                value: array.slice(start, end - start),
                indices: (start..end).collect(),
                filter: BooleanArray::from(vec![true; end - start]),
                growing_groups: end,
            }
        })
        .collect()
}

fn update(
    acc: &mut dyn GroupsAccumulator,
    batches: &[Batch],
    groups: usize,
    growing: bool,
    method: Method,
) -> Result<()> {
    for batch in batches {
        let values = [batch.value.clone(), batch.value.clone()];
        let values = match method {
            Method::Native9fCompactMin => &values[..1],
            Method::PlannerOrderedMinBy => &values[..],
        };
        acc.update_batch(
            values,
            &batch.indices,
            Some(&batch.filter),
            if growing {
                batch.growing_groups
            } else {
                groups
            },
        )?;
    }
    Ok(())
}

fn assert_values(actual: &ArrayRef, groups: usize, offset: usize, sparse: bool) {
    let value = actual.as_any().downcast_ref::<StructArray>().unwrap();
    assert_eq!(value.null_count(), 0);
    let distance = value
        .column(0)
        .as_any()
        .downcast_ref::<Float64Array>()
        .unwrap();
    let hops = value
        .column(1)
        .as_any()
        .downcast_ref::<Int64Array>()
        .unwrap();
    let parent = value
        .column(2)
        .as_any()
        .downcast_ref::<Int64Array>()
        .unwrap();
    assert_eq!(
        distance.null_count() + hops.null_count() + parent.null_count(),
        0
    );
    for i in 0..actual.len() {
        assert_eq!(
            distance.value(i),
            if sparse && offset + i < BATCH {
                0.5
            } else {
                1.0
            }
        );
        assert_eq!(hops.value(i), 2);
        assert_eq!(parent.value(i), (offset + i) as i64 - groups as i64 / 2);
    }
}

fn run(groups: usize, method: Method) -> Result<()> {
    println!(
        "{}",
        json!({"groups":groups,"batch_rows":BATCH,"method":format!("{method:?}"),
        "contract":"same nonnull full(distance Float64,hops Int64,parent Int64) payload and complete key; finite unique total keys; signed parent IDs; filter true",
        "allocator_scope":"requested System allocation bytes/counts; separate process lifetime getrusage RSS; neither MiMalloc nor native Sail physical allocation",
        "boundary":"single-thread public grouped accumulator phases; exploratory shared native host; no graph input or whole-query timing"})
    );
    let metadata = json!({"rows":groups});
    let phase = meter::Phase::start();
    let original = input(groups, 2.0);
    phase.finish(
        "arrow_input_control",
        0,
        original.get_array_memory_size(),
        metadata,
    );
    let better = input(groups, 1.0);
    let sparse = input(groups, 0.5).slice(0, groups.min(BATCH));
    let original_batches = batches(&original);
    let better_batches = batches(&better);
    let sparse_batches = batches(&sparse);
    let mut acc = accumulator(original.data_type(), method)?;
    for (name, input, growing) in [
        ("first_update", &original_batches, true),
        ("repeat_identical", &original_batches, false),
        ("repeat_improving", &better_batches, false),
        ("sparse_improving", &sparse_batches, false),
    ] {
        let rows: usize = input.iter().map(|batch| batch.value.len()).sum();
        let metadata = json!({"rows":rows,"batches":input.len(),"groups":groups});
        let phase = meter::Phase::start();
        update(acc.as_mut(), input, groups, growing, method)?;
        phase.finish(name, acc.size(), 0, metadata);
    }
    let metadata = json!({"emitted_groups":groups});
    let phase = meter::Phase::start();
    let result = acc.evaluate(EmitTo::All)?;
    phase.finish(
        "evaluate_all",
        acc.size(),
        result.get_array_memory_size(),
        metadata,
    );
    assert_eq!(result.len(), groups);
    assert_values(&result, groups, 0, true);
    for emitted in [groups, 1, groups / 2] {
        let mut original_acc = accumulator(original.data_type(), method)?;
        update(original_acc.as_mut(), &better_batches, groups, true, method)?;
        let metadata = json!({"emitted_groups":emitted,"remaining_groups":groups-emitted});
        let phase = meter::Phase::start();
        let state = original_acc.state(if emitted == groups {
            EmitTo::All
        } else {
            EmitTo::First(emitted)
        })?;
        let bytes = state
            .iter()
            .map(|array| array.get_array_memory_size())
            .sum();
        phase.finish("state_emission", original_acc.size(), bytes, metadata);
        let indices: Vec<usize> = (0..emitted).collect();
        let mut merged = accumulator(original.data_type(), method)?;
        let metadata = json!({"rows":emitted,"state_arrays":state.len()});
        let phase = meter::Phase::start();
        merged.merge_batch(&state, &indices, emitted)?;
        phase.finish("merge_emitted_state", merged.size(), 0, metadata);
        let emitted_result = merged.evaluate(EmitTo::All)?;
        assert_eq!(emitted_result.len(), emitted);
        assert_values(&emitted_result, groups, 0, false);
        if emitted < groups {
            let tail = original_acc.evaluate(EmitTo::All)?;
            assert_eq!(tail.len(), groups - emitted);
            assert_values(&tail, groups, emitted, false);
        }
    }
    println!(
        "{}",
        json!({"checks":"passed","groups":groups,"method":format!("{method:?}")})
    );
    Ok(())
}

fn main() -> Result<()> {
    let mut args = std::env::args().skip(1);
    let groups: usize = args
        .next()
        .expect("groups required")
        .parse()
        .expect("numeric groups");
    assert!([4096, 100_000].contains(&groups));
    let method = match args.next().as_deref() {
        Some("tuple-min") => Method::Native9fCompactMin,
        Some("min-by") => Method::PlannerOrderedMinBy,
        _ => panic!("tuple-min|min-by required"),
    };
    assert!(args.next().is_none());
    run(groups, method)
}

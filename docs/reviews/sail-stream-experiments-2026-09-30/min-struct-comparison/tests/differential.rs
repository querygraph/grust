use std::sync::Arc;
use arrow::array::{Array, ArrayRef, BooleanArray, Float64Array, Int64Array, StructArray};
use arrow::buffer::NullBuffer;
use arrow::datatypes::{DataType, Field};
use datafusion_expr::EmitTo;
use min_struct_comparison::accumulator;

fn next(seed: &mut u64) -> u64 {
    *seed ^= *seed << 13; *seed ^= *seed >> 7; *seed ^= *seed << 17; *seed
}

fn batch(seed: &mut u64, rows: usize) -> (ArrayRef, BooleanArray) {
    let bits = [0u64, 1 << 63, 1.0f64.to_bits(), (-1.0f64).to_bits(),
        f64::INFINITY.to_bits(), f64::NEG_INFINITY.to_bits(),
        0x7ff8_0000_0000_0001, 0x7ff8_0000_0000_0002,
        0xfff8_0000_0000_0001, 0x7ff0_0000_0000_0001];
    let ints = [i64::MIN, i64::MAX, -17, -1, 0, 1, 2, 999];
    let distance: Vec<_> = (0..rows).map(|_| {
        let r = next(seed); (r % 7 != 0).then_some(f64::from_bits(bits[r as usize % bits.len()]))
    }).collect();
    let mut integer = || (0..rows).map(|_| {
        let r = next(seed); (r % 7 != 0).then_some(ints[r as usize % ints.len()])
    }).collect::<Vec<_>>();
    let hops = integer(); let parents = integer();
    let root: Vec<bool> = (0..rows).map(|_| next(seed) % 9 != 0).collect();
    let filter: BooleanArray = (0..rows).map(|_| {
        let r = next(seed); (r % 5 != 0).then_some(r % 3 != 0)
    }).collect();
    let fields = vec![Field::new("distance", DataType::Float64, true),
                      Field::new("hops", DataType::Int64, true),
                      Field::new("parent", DataType::Int64, true)].into();
    (Arc::new(StructArray::new(fields, vec![Arc::new(Float64Array::from(distance)),
        Arc::new(Int64Array::from(hops)), Arc::new(Int64Array::from(parents))],
        Some(NullBuffer::from(root)))), filter)
}

fn same(left: &ArrayRef, right: &ArrayRef) {
    assert_eq!(left.data_type(), right.data_type());
    assert_eq!(left.len(), right.len());
    let left = left.as_any().downcast_ref::<StructArray>().unwrap();
    let right = right.as_any().downcast_ref::<StructArray>().unwrap();
    for row in 0..left.len() {
        assert_eq!(left.is_null(row), right.is_null(row), "root row {row}");
        if left.is_null(row) { continue; }
        for col in 0..3 {
            let l = left.column(col); let r = right.column(col);
            assert_eq!(l.is_null(row), r.is_null(row), "child {col} row {row}");
            if l.is_null(row) { continue; }
            if col == 0 {
                let l = l.as_any().downcast_ref::<Float64Array>().unwrap().value(row).to_bits();
                let r = r.as_any().downcast_ref::<Float64Array>().unwrap().value(row).to_bits();
                assert_eq!(l, r, "float bits row {row}");
            } else {
                assert_eq!(l.as_any().downcast_ref::<Int64Array>().unwrap().value(row),
                           r.as_any().downcast_ref::<Int64Array>().unwrap().value(row));
            }
        }
    }
}

#[test]
fn randomized_batches_filter_child_null_nan_merge_and_prefix_match_original() {
    for initial_seed in 1..=64 {
        let mut seed = initial_seed;
        let groups = 3 + next(&mut seed) as usize % 21;
        let (example, _) = batch(&mut seed, 1);
        let mut original = accumulator(example.data_type(), false);
        let mut compact = accumulator(example.data_type(), true);
        for step in 0..12 {
            let rows = 1 + next(&mut seed) as usize % 127;
            let (array, filter) = batch(&mut seed, rows);
            let indices: Vec<usize> = (0..rows).map(|_| next(&mut seed) as usize % groups).collect();
            let values = [array];
            let filter = (step % 3 != 0).then_some(&filter);
            same(&original.convert_to_state(&values, filter).unwrap()[0],
                 &compact.convert_to_state(&values, filter).unwrap()[0]);
            if step % 4 == 0 {
                original.merge_batch(&values, &indices, groups).unwrap();
                compact.merge_batch(&values, &indices, groups).unwrap();
            } else {
                original.update_batch(&values, &indices, filter, groups).unwrap();
                compact.update_batch(&values, &indices, filter, groups).unwrap();
            }
            if step == 3 || step == 7 {
                same(&original.state(EmitTo::First(groups / 3)).unwrap()[0],
                     &compact.state(EmitTo::First(groups / 3)).unwrap()[0]);
            }
        }
        same(&original.evaluate(EmitTo::All).unwrap(), &compact.evaluate(EmitTo::All).unwrap());
    }
}

#[test]
fn partial_state_roundtrip_and_all_unseen_groups_match_original() {
    let mut seed = 991;
    let (array, filter) = batch(&mut seed, 64);
    for all_filtered in [false, true] {
        let false_filter = BooleanArray::from(vec![false; 64]);
        let filter = if all_filtered { &false_filter } else { &filter };
        let mut original = accumulator(array.data_type(), false);
        let mut compact = accumulator(array.data_type(), true);
        let indices: Vec<_> = (0..64).map(|i| i % 11).collect();
        original.update_batch(&[array.clone()], &indices, Some(filter), 11).unwrap();
        compact.update_batch(&[array.clone()], &indices, Some(filter), 11).unwrap();
        let original_state = original.state(EmitTo::All).unwrap();
        let compact_state = compact.state(EmitTo::All).unwrap();
        same(&original_state[0], &compact_state[0]);
        let indices: Vec<_> = (0..11).map(|i| i % 3).collect();
        original.merge_batch(&original_state, &indices, 3).unwrap();
        compact.merge_batch(&compact_state, &indices, 3).unwrap();
        same(&original.evaluate(EmitTo::All).unwrap(), &compact.evaluate(EmitTo::All).unwrap());
    }
}

#[test]
fn nonnullable_children_and_field_metadata_survive_filter_and_unseen_groups() {
    let fields = vec![
        Field::new("d", DataType::Float64, false).with_metadata(
            std::collections::HashMap::from([("meaning".into(), "distance".into())])),
        Field::new("h", DataType::Int64, false), Field::new("p", DataType::Int64, false),
    ].into();
    let array: ArrayRef = Arc::new(StructArray::new(fields, vec![
        Arc::new(Float64Array::from(vec![0.0, -0.0, 0.0])),
        Arc::new(Int64Array::from(vec![0, 2, 1])),
        Arc::new(Int64Array::from(vec![0, i64::MIN, i64::MAX])),
    ], None));
    let filter = BooleanArray::from(vec![false, true, true]);
    let mut original = accumulator(array.data_type(), false);
    let mut compact = accumulator(array.data_type(), true);
    same(&original.convert_to_state(&[array.clone()], Some(&filter)).unwrap()[0],
         &compact.convert_to_state(&[array.clone()], Some(&filter)).unwrap()[0]);
    original.update_batch(&[array.clone()], &[0, 1, 1], Some(&filter), 3).unwrap();
    compact.update_batch(&[array.clone()], &[0, 1, 1], Some(&filter), 3).unwrap();
    same(&original.evaluate(EmitTo::All).unwrap(), &compact.evaluate(EmitTo::All).unwrap());
}

#[test]
fn original_empty_emission_panics_but_candidate_returns_typed_empty() {
    let (array, _) = batch(&mut 991, 1);
    for emit in [EmitTo::All, EmitTo::First(0)] {
        let mut original = accumulator(array.data_type(), false);
        let original = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| original.evaluate(emit)));
        assert!(original.is_err(), "control: original constructs MutableArrayData with zero sources");
        let mut compact = accumulator(array.data_type(), true);
        let result = compact.evaluate(emit).unwrap();
        assert_eq!(result.len(), 0);
        assert_eq!(result.data_type(), array.data_type());
    }
}

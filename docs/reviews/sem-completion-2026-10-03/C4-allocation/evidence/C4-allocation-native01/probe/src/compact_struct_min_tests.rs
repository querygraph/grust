use std::collections::HashMap;

use super::*;
use datafusion::arrow::array::{Float64Array, Int64Array};
use datafusion::arrow::datatypes::{Field, Fields};
use datafusion::common::scalar::partial_cmp_struct;

fn fields(nullable: bool) -> Fields {
    vec![
        Field::new("distance", DataType::Float64, nullable)
            .with_metadata(HashMap::from([("unit".into(), "custom".into())])),
        Field::new("hops", DataType::Int64, nullable),
        Field::new("parent", DataType::Int64, nullable),
    ]
    .into()
}
fn rows(input: &[Group], fields: Fields) -> ArrayRef {
    Arc::new(StructArray::new(
        fields,
        vec![
            Arc::new(Float64Array::from_iter(
                input.iter().map(|r| (r.valid & 1 != 0).then_some(r.first)),
            )),
            Arc::new(Int64Array::from_iter(
                input.iter().map(|r| (r.valid & 2 != 0).then_some(r.second)),
            )),
            Arc::new(Int64Array::from_iter(
                input.iter().map(|r| (r.valid & 4 != 0).then_some(r.third)),
            )),
        ],
        Some(NullBuffer::from_iter(
            input.iter().map(|r| r.valid & PRESENT != 0),
        )),
    ))
}
fn row(first: f64, second: i64, third: i64, children: u8) -> Group {
    Group {
        first,
        second,
        third,
        valid: PRESENT | children,
    }
}
fn assert_rows(actual: &ArrayRef, expected: &[Group]) {
    let actual = actual.as_struct();
    assert_eq!(actual.len(), expected.len());
    for (i, expected) in expected.iter().enumerate() {
        assert_eq!(actual.is_valid(i), expected.valid & PRESENT != 0);
        let floats = actual.column(0).as_primitive::<Float64Type>();
        let seconds = actual.column(1).as_primitive::<Int64Type>();
        let thirds = actual.column(2).as_primitive::<Int64Type>();
        assert_eq!(floats.is_valid(i), expected.valid & 1 != 0);
        assert_eq!(seconds.is_valid(i), expected.valid & 2 != 0);
        assert_eq!(thirds.is_valid(i), expected.valid & 4 != 0);
        if expected.valid & 1 != 0 {
            assert_eq!(floats.value(i).to_bits(), expected.first.to_bits());
        }
        if expected.valid & 2 != 0 {
            assert_eq!(seconds.value(i), expected.second);
        }
        if expected.valid & 4 != 0 {
            assert_eq!(thirds.value(i), expected.third);
        }
    }
}

#[test]
fn typed_comparison_matches_arrow_struct_order_for_all_child_masks() {
    let cases = [
        (f64::NEG_INFINITY, i64::MIN, i64::MAX),
        (-1.0, -1, 0),
        (-0.0, 0, -1),
        (0.0, 0, i64::MIN),
        (1.0, i64::MAX, i64::MIN),
        (f64::INFINITY, 2, 3),
        (f64::from_bits(0x7ff8_0000_0000_0001), 2, i64::MAX),
        (f64::from_bits(0xfff8_0000_0000_0001), 2, i64::MAX),
        (f64::from_bits(0x7ff0_0000_0000_0001), 0, 0),
    ];
    let mut groups = Vec::new();
    for (first, second, third) in cases {
        for valid in 0..8 {
            groups.push(row(first, second, third, valid));
        }
    }
    let arrays: Vec<_> = groups
        .iter()
        .map(|group| rows(&[*group], fields(true)))
        .collect();
    for (i, a) in groups.iter().enumerate() {
        for (j, b) in groups.iter().enumerate() {
            assert_eq!(
                a.precedes(b),
                partial_cmp_struct(arrays[i].as_struct(), arrays[j].as_struct())
                    == Some(Ordering::Less),
                "row {i}, row {j}"
            );
        }
    }
}

#[test]
fn filters_root_nulls_first_ties_and_null_children_are_distinct() -> Result<()> {
    let first = row(5.0, -7, 8, 2); // first field is NULL
    let equal = row(-100.0, -7, 8, 7); // skipped first field makes a full tie
    let input = rows(
        &[
            first,
            equal,
            row(f64::NEG_INFINITY, i64::MIN, i64::MIN, 7),
            Group::default(),
            row(-999.0, i64::MIN, 0, 7),
            row(0.0, 0, 0, 0), // valid struct whose three children are NULL
        ],
        fields(true),
    );
    let filter = BooleanArray::from(vec![
        Some(true),
        Some(true),
        Some(false),
        Some(true),
        None,
        Some(true),
    ]);
    let mut acc = new(input.data_type())?;
    acc.update_batch(
        std::slice::from_ref(&input),
        &[0, 0, 0, 1, 1, 2],
        Some(&filter),
        4,
    )?;
    let output = acc.evaluate(EmitTo::All)?;
    assert_eq!(output.data_type(), input.data_type());
    assert_rows(
        &output,
        &[first, Group::default(), row(0.0, 0, 0, 0), Group::default()],
    );
    let converted = acc.convert_to_state(&[input], Some(&filter))?;
    assert_eq!(converted.len(), 1);
    assert_eq!(converted[0].null_count(), 3);
    let mut merged = new(converted[0].data_type())?;
    merged.merge_batch(&converted, &[0, 0, 0, 1, 1, 2], 4)?;
    assert_rows(
        &merged.evaluate(EmitTo::All)?,
        &[first, Group::default(), row(0.0, 0, 0, 0), Group::default()],
    );
    Ok(())
}

#[test]
fn state_merge_prefix_shift_and_capacity_accounting_remain_valid() -> Result<()> {
    let values: Vec<_> = (0..37).map(|i| row(i as f64, i, -i, 7)).collect();
    let array = rows(&values, fields(false));
    let mut acc = CompactStructMin {
        data_type: array.data_type().clone(),
        groups: Vec::with_capacity(128),
    };
    let fixed = size_of_val(&acc) + acc.data_type.size() - size_of::<DataType>();
    acc.update_batch(&[array], &(0..37).collect::<Vec<_>>(), None, 37)?;
    assert_eq!(acc.size(), fixed + 128 * size_of::<Group>());
    let prefix = acc.state(EmitTo::First(3))?;
    assert_rows(&prefix[0], &values[..3]);
    // First(3) retains the original allocation. Size must not shrink to len.
    assert_eq!(acc.size(), fixed + 128 * size_of::<Group>());
    let replacement = row(-1.0, -1, -1, 7);
    acc.update_batch(&[rows(&[replacement], fields(false))], &[0], None, 34)?;
    let mut expected = values[3..].to_vec();
    expected[0] = replacement;
    assert_rows(&acc.evaluate(EmitTo::All)?, &expected);
    assert_eq!(acc.size(), fixed);
    let mut merged = new(&acc.data_type)?;
    merged.merge_batch(&prefix, &[2, 0, 1], 4)?;
    assert_rows(
        &merged.evaluate(EmitTo::All)?,
        &[values[1], values[2], values[0], Group::default()],
    );
    assert_eq!(acc.evaluate(EmitTo::All)?.len(), 0);
    assert_eq!(acc.evaluate(EmitTo::First(0))?.len(), 0);
    Ok(())
}

#[test]
fn specialization_rejects_other_shapes_and_keeps_field_metadata() -> Result<()> {
    let supported = DataType::Struct(fields(true));
    assert!(supports_type(&supported));
    for ty in [
        DataType::Float64,
        DataType::Struct(Fields::empty()),
        DataType::Struct(vec![Field::new("x", DataType::Float64, true)].into()),
        DataType::Struct(
            vec![
                Field::new("a", DataType::Float32, true),
                Field::new("b", DataType::Int64, true),
                Field::new("c", DataType::Int64, true),
            ]
            .into(),
        ),
        DataType::Struct(
            vec![
                Field::new("a", DataType::Float64, true),
                Field::new("b", DataType::UInt64, true),
                Field::new("c", DataType::Int64, true),
            ]
            .into(),
        ),
        DataType::Struct(
            vec![
                Field::new("a", DataType::Float64, true),
                Field::new("b", DataType::Int64, true),
                Field::new("c", supported.clone(), true),
            ]
            .into(),
        ),
    ] {
        assert!(!supports_type(&ty));
        assert!(new(&ty).is_err());
    }
    let mut acc = new(&supported)?;
    let output = acc.evaluate(EmitTo::All)?;
    assert_eq!(output.data_type(), &supported);
    Ok(())
}

//! Compact grouped MIN for flat (Float64, Int64, Int64) structs.
//!
//! Comparison deliberately matches DataFusion's `partial_cmp_struct`: skip a
//! field unless both children are valid, use Arrow's total float order, and keep
//! the first value on a full tie. This is not SQL row comparison with NULLS LAST.
use std::cmp::Ordering;
use std::mem::{size_of, size_of_val};
use std::sync::Arc;

use datafusion::arrow::array::{
    Array, ArrayRef, AsArray, BooleanArray, Float64Builder, Int64Builder, NullBufferBuilder,
    StructArray,
};
use datafusion::arrow::buffer::NullBuffer;
use datafusion::arrow::datatypes::{DataType, Float64Type, Int64Type};
use datafusion::common::{Result, internal_err};
use datafusion::logical_expr::{EmitTo, GroupsAccumulator};

pub(super) fn supports_type(data_type: &DataType) -> bool {
    matches!(data_type, DataType::Struct(fields) if fields.len() == 3
        && fields[0].data_type() == &DataType::Float64
        && fields[1].data_type() == &DataType::Int64
        && fields[2].data_type() == &DataType::Int64)
}

pub(super) fn new(data_type: &DataType) -> Result<Box<dyn GroupsAccumulator>> {
    if !supports_type(data_type) {
        return internal_err!("compact struct MIN requires (Float64, Int64, Int64)");
    }
    Ok(Box::new(CompactStructMin {
        data_type: data_type.clone(),
        groups: Vec::new(),
    }))
}

const PRESENT: u8 = 8;

/// One owned inline value per group, including child validity and presence.
/// Presence distinguishes an unseen group from a valid struct of three nulls.
#[derive(Clone, Copy, Default)]
struct Group {
    first: f64,
    second: i64,
    third: i64,
    valid: u8,
}
impl Group {
    fn precedes(&self, other: &Self) -> bool {
        let both = self.valid & other.valid;
        if both & 1 != 0 {
            match self.first.total_cmp(&other.first) {
                Ordering::Less => return true,
                Ordering::Greater => return false,
                Ordering::Equal => {}
            }
        }
        if both & 2 != 0 {
            match self.second.cmp(&other.second) {
                Ordering::Less => return true,
                Ordering::Greater => return false,
                Ordering::Equal => {}
            }
        }
        both & 4 != 0 && self.third < other.third
    }
}

struct CompactStructMin {
    data_type: DataType,
    groups: Vec<Group>,
}
impl GroupsAccumulator for CompactStructMin {
    fn update_batch(
        &mut self,
        values: &[ArrayRef],
        group_indices: &[usize],
        opt_filter: Option<&BooleanArray>,
        total_num_groups: usize,
    ) -> Result<()> {
        let array = &values[0];
        assert_eq!(array.len(), group_indices.len());
        assert_eq!(array.data_type(), &self.data_type);
        if let Some(filter) = opt_filter {
            assert_eq!(filter.len(), array.len());
        }
        let array = array.as_struct();
        let first = array.column(0).as_primitive::<Float64Type>();
        let second = array.column(1).as_primitive::<Int64Type>();
        let third = array.column(2).as_primitive::<Int64Type>();
        self.groups.resize(total_num_groups, Group::default());
        for (row, &group_index) in group_indices.iter().enumerate() {
            if array.is_null(row)
                || opt_filter.is_some_and(|filter| filter.is_null(row) || !filter.value(row))
            {
                continue;
            }
            let candidate = Group {
                first: first.value(row),
                second: second.value(row),
                third: third.value(row),
                valid: PRESENT
                    | u8::from(first.is_valid(row))
                    | (u8::from(second.is_valid(row)) << 1)
                    | (u8::from(third.is_valid(row)) << 2),
            };
            let current = &mut self.groups[group_index];
            if current.valid & PRESENT == 0 || candidate.precedes(current) {
                *current = candidate;
            }
        }
        Ok(())
    }

    fn evaluate(&mut self, emit_to: EmitTo) -> Result<ArrayRef> {
        let groups = emit_to.take_needed(&mut self.groups);
        let mut first = Float64Builder::with_capacity(groups.len());
        let mut second = Int64Builder::with_capacity(groups.len());
        let mut third = Int64Builder::with_capacity(groups.len());
        let mut validity = NullBufferBuilder::new(groups.len());
        for group in groups {
            first.append_option((group.valid & 1 != 0).then_some(group.first));
            second.append_option((group.valid & 2 != 0).then_some(group.second));
            third.append_option((group.valid & 4 != 0).then_some(group.third));
            validity.append(group.valid & PRESENT != 0);
        }
        let DataType::Struct(fields) = &self.data_type else {
            return internal_err!("compact struct MIN has a non-struct type");
        };
        Ok(Arc::new(StructArray::try_new(
            fields.clone(),
            vec![
                Arc::new(first.finish()),
                Arc::new(second.finish()),
                Arc::new(third.finish()),
            ],
            validity.finish(),
        )?))
    }

    fn state(&mut self, emit_to: EmitTo) -> Result<Vec<ArrayRef>> {
        self.evaluate(emit_to).map(|array| vec![array])
    }

    fn merge_batch(
        &mut self,
        values: &[ArrayRef],
        group_indices: &[usize],
        total_num_groups: usize,
    ) -> Result<()> {
        self.update_batch(values, group_indices, None, total_num_groups)
    }

    fn convert_to_state(
        &self,
        values: &[ArrayRef],
        opt_filter: Option<&BooleanArray>,
    ) -> Result<Vec<ArrayRef>> {
        let array = &values[0];
        assert_eq!(array.data_type(), &self.data_type);
        let array = array.as_struct();
        let filtered = opt_filter.and_then(|filter| {
            assert_eq!(filter.len(), array.len());
            let values = NullBuffer::new(filter.values().clone());
            NullBuffer::union(Some(&values), filter.nulls())
        });
        let nulls = NullBuffer::union(filtered.as_ref(), array.nulls());
        Ok(vec![Arc::new(StructArray::try_new(
            array.fields().clone(),
            array.columns().to_vec(),
            nulls,
        )?)])
    }

    fn size(&self) -> usize {
        // Include spare capacity retained after EmitTo::First, not just live
        // groups. Schema storage is fixed (three fields), independent of groups.
        size_of_val(self) + self.data_type.size() - size_of::<DataType>()
            + self.groups.capacity() * size_of::<Group>()
    }
}

#[cfg(test)]
#[path = "compact_struct_min_tests.rs"]
mod tests;

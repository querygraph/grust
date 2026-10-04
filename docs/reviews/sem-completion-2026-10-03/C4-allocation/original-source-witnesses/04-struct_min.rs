use std::sync::{Arc, LazyLock};

use datafusion::arrow::datatypes::{DataType, FieldRef};
use datafusion::common::{Result, ScalarValue};
use datafusion::functions_aggregate::min_max::Min;
use datafusion::logical_expr::function::{AccumulatorArgs, StateFieldsArgs};
use datafusion::logical_expr::utils::AggregateOrderSensitivity;
use datafusion::logical_expr::{
    Accumulator, AggregateUDF, AggregateUDFImpl, Documentation, GroupsAccumulator, ReversedUDAF,
    SetMonotonicity, Signature, StatisticsArgs,
};

use crate::aggregate::compact_struct_min;

/// DataFusion MIN with compact grouped state for a fixed three-field struct.
///
/// Scalar, sliding, and other grouped types keep DataFusion's implementation.
/// The ordinary name is intentional: the remote codec encodes this concrete
/// implementation explicitly so worker registry lookup cannot replace it.
#[derive(Debug, Default, PartialEq, Eq, Hash)]
pub struct StructMin {
    inner: Min,
}

pub fn supports_struct_min(data_type: &DataType) -> bool {
    compact_struct_min::supports_type(data_type)
}

pub fn struct_min_udaf() -> Arc<AggregateUDF> {
    static UDAF: LazyLock<Arc<AggregateUDF>> =
        LazyLock::new(|| Arc::new(AggregateUDF::from(StructMin::default())));
    Arc::clone(&UDAF)
}

impl AggregateUDFImpl for StructMin {
    fn name(&self) -> &str {
        self.inner.name()
    }

    fn signature(&self) -> &Signature {
        self.inner.signature()
    }

    fn return_type(&self, arg_types: &[DataType]) -> Result<DataType> {
        self.inner.return_type(arg_types)
    }

    fn return_field(&self, arg_fields: &[FieldRef]) -> Result<FieldRef> {
        self.inner.return_field(arg_fields)
    }

    fn is_nullable(&self) -> bool {
        self.inner.is_nullable()
    }

    fn accumulator(&self, args: AccumulatorArgs) -> Result<Box<dyn Accumulator>> {
        self.inner.accumulator(args)
    }

    fn state_fields(&self, args: StateFieldsArgs) -> Result<Vec<FieldRef>> {
        self.inner.state_fields(args)
    }

    fn groups_accumulator_supported(&self, args: AccumulatorArgs) -> bool {
        self.inner.groups_accumulator_supported(args)
    }

    fn create_groups_accumulator(
        &self,
        args: AccumulatorArgs,
    ) -> Result<Box<dyn GroupsAccumulator>> {
        if supports_struct_min(args.return_type()) {
            compact_struct_min::new(args.return_type())
        } else {
            self.inner.create_groups_accumulator(args)
        }
    }

    fn create_sliding_accumulator(&self, args: AccumulatorArgs) -> Result<Box<dyn Accumulator>> {
        self.inner.create_sliding_accumulator(args)
    }

    fn is_descending(&self) -> Option<bool> {
        self.inner.is_descending()
    }

    fn value_from_stats(&self, args: &StatisticsArgs) -> Option<ScalarValue> {
        self.inner.value_from_stats(args)
    }

    fn order_sensitivity(&self) -> AggregateOrderSensitivity {
        self.inner.order_sensitivity()
    }

    fn coerce_types(&self, arg_types: &[DataType]) -> Result<Vec<DataType>> {
        self.inner.coerce_types(arg_types)
    }

    fn reverse_expr(&self) -> ReversedUDAF {
        self.inner.reverse_expr()
    }

    fn documentation(&self) -> Option<&Documentation> {
        self.inner.documentation()
    }

    fn set_monotonicity(&self, data_type: &DataType) -> SetMonotonicity {
        self.inner.set_monotonicity(data_type)
    }
}

#[cfg(test)]
#[path = "struct_min_tests.rs"]
mod tests;

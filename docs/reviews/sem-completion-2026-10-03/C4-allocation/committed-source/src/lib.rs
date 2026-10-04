//! Exact native9f compact source and public DF55.1 ordered LAST_VALUE factory.
extern crate self as datafusion;
pub use arrow;
pub use datafusion_common as common;
pub use datafusion_expr as logical_expr;

use arrow::compute::SortOptions;
use arrow::datatypes::{DataType, Field, Schema};
use datafusion_common::{Result, internal_err};
use datafusion_expr::GroupsAccumulator;
use datafusion_expr::function::AccumulatorArgs;
use datafusion_functions_aggregate::first_last::last_value_udaf;
use datafusion_physical_expr::{PhysicalExpr, PhysicalSortExpr, expressions::Column};
use std::sync::Arc;

mod compact_struct_min;

#[derive(Clone, Copy, Debug)]
pub enum Method {
    Native9fCompactMin,
    PlannerOrderedMinBy,
}

pub fn accumulator(data_type: &DataType, method: Method) -> Result<Box<dyn GroupsAccumulator>> {
    match method {
        Method::Native9fCompactMin => compact_struct_min::new(data_type),
        Method::PlannerOrderedMinBy => {
            let value = Arc::new(Field::new("candidate", data_type.clone(), false));
            let schema = Schema::new(vec![value.clone(), value.clone()]);
            let expressions: Vec<Arc<dyn PhysicalExpr>> =
                vec![Arc::new(Column::new("candidate", 0))];
            let order = [PhysicalSortExpr {
                expr: Arc::new(Column::new("candidate", 1)),
                options: SortOptions {
                    descending: true,
                    nulls_first: true,
                },
            }];
            let fields = [value.clone()];
            let args = AccumulatorArgs {
                return_field: value,
                schema: &schema,
                ignore_nulls: false,
                order_bys: &order,
                is_reversed: false,
                name: "min_by_full_candidate",
                is_distinct: false,
                exprs: &expressions,
                expr_fields: &fields,
            };
            let udf = last_value_udaf();
            if !udf.groups_accumulator_supported(args.clone()) {
                return internal_err!("ordered full-struct grouped factory unavailable");
            }
            udf.create_groups_accumulator(args)
        }
    }
}

#[cfg(test)]
#[path = "pair_tests.rs"]
mod pair_tests;

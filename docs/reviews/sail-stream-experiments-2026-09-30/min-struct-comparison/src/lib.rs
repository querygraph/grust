extern crate self as datafusion;
pub use arrow;
pub use datafusion_common as common;
pub use datafusion_expr as logical_expr;

include!(concat!(env!("OUT_DIR"), "/modules.rs"));

pub fn accumulator(data_type: &arrow::datatypes::DataType, compact: bool)
    -> Box<dyn datafusion_expr::GroupsAccumulator>
{
    if compact { candidate::new(data_type).unwrap() }
    else { Box::new(original::MinMaxStructAccumulator::new_min(data_type.clone())) }
}

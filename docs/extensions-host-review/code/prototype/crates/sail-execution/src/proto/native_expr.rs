//! Native scalar return fields carry extension metadata that DataFusion's
//! standard scalar-expression protobuf currently omits.
use std::sync::Arc;

use datafusion::arrow::datatypes::Schema;
use datafusion::common::metadata::FieldMetadata;
use datafusion::common::{Result, plan_datafusion_err};
use datafusion::execution::FunctionRegistry;
use datafusion::physical_expr::expressions::{CastExpr, Literal};
use datafusion::physical_expr::{PhysicalExpr, ScalarFunctionExpr};
use datafusion_proto::physical_plan::to_proto::serialize_physical_expr_with_converter;
use datafusion_proto::physical_plan::{
    PhysicalExtensionCodec, PhysicalPlanDecodeContext, PhysicalProtoConverterExtension,
};
use datafusion_proto::protobuf::{PhysicalExprNode, PhysicalExtensionExprNode, physical_expr_node};
use sail_common_datafusion::native_scalar::OwnedScalar;
use serde::{Deserialize, Serialize};

use super::decode::try_decode_field_ref;
use super::encode::try_encode_field_ref;

const PREFIX: &[u8] = b"SAIL_NATIVE_SCALAR_EXPR_V1\0";
const LITERAL_PREFIX: &[u8] = b"SAIL_METADATA_LITERAL_V1\0";
const CAST_PREFIX: &[u8] = b"SAIL_METADATA_CAST_V1\0";
const MAX_DESCRIPTOR: usize = 1024 * 1024;

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Descriptor {
    name: String,
    udf: Vec<u8>,
    field: Vec<u8>,
    nullable: bool,
}

pub(super) fn encode(
    expr: &Arc<dyn PhysicalExpr>,
    codec: &dyn PhysicalExtensionCodec,
    converter: &dyn PhysicalProtoConverterExtension,
) -> Result<Option<PhysicalExprNode>> {
    if let Some(cast) = expr.downcast_ref::<CastExpr>()
        && cast.has_explicit_metadata()
        && !cast.target_field().metadata().is_empty()
    {
        let bytes = try_encode_field_ref(cast.target_field())?;
        if bytes.len() > MAX_DESCRIPTOR {
            return Err(plan_datafusion_err!("cast field descriptor too large"));
        }
        return Ok(Some(PhysicalExprNode {
            expr_type: Some(physical_expr_node::ExprType::Extension(
                PhysicalExtensionExprNode {
                    expr: [CAST_PREFIX, bytes.as_slice()].concat(),
                    inputs: vec![serialize_physical_expr_with_converter(
                        expr, codec, converter,
                    )?],
                },
            )),
            expr_id: expr.expression_id(),
        }));
    }
    if expr.downcast_ref::<Literal>().is_some() {
        let field = expr.return_field(&Schema::empty())?;
        if !field.metadata().is_empty() {
            let bytes = try_encode_field_ref(&field)?;
            if bytes.len() > MAX_DESCRIPTOR {
                return Err(plan_datafusion_err!("literal field descriptor too large"));
            }
            return Ok(Some(PhysicalExprNode {
                expr_type: Some(physical_expr_node::ExprType::Extension(
                    PhysicalExtensionExprNode {
                        expr: [LITERAL_PREFIX, bytes.as_slice()].concat(),
                        inputs: vec![serialize_physical_expr_with_converter(
                            expr, codec, converter,
                        )?],
                    },
                )),
                expr_id: expr.expression_id(),
            }));
        }
    }
    let Some(scalar) = expr.downcast_ref::<ScalarFunctionExpr>() else {
        return Ok(None);
    };
    let field = expr.return_field(&Schema::empty())?;
    if !scalar.fun().inner().is::<OwnedScalar>() && field.metadata().is_empty() {
        return Ok(None);
    }
    let mut udf = vec![];
    codec.try_encode_udf(scalar.fun(), &mut udf)?;
    let descriptor = Descriptor {
        name: scalar.fun().name().to_owned(),
        udf,
        field: try_encode_field_ref(&field)?,
        nullable: scalar.nullable(),
    };
    let bytes = serde_json::to_vec(&descriptor)
        .map_err(|e| plan_datafusion_err!("native scalar descriptor: {e}"))?;
    if bytes.len() > MAX_DESCRIPTOR {
        return Err(plan_datafusion_err!("native scalar descriptor too large"));
    }
    let inputs = scalar
        .args()
        .iter()
        .map(|arg| converter.physical_expr_to_proto(arg, codec))
        .collect::<Result<_>>()?;
    Ok(Some(PhysicalExprNode {
        expr_type: Some(physical_expr_node::ExprType::Extension(
            PhysicalExtensionExprNode {
                expr: [PREFIX, bytes.as_slice()].concat(),
                inputs,
            },
        )),
        expr_id: expr.expression_id(),
    }))
}

pub(super) fn decode(
    proto: &PhysicalExprNode,
    schema: &Schema,
    ctx: &PhysicalPlanDecodeContext<'_>,
    converter: &dyn PhysicalProtoConverterExtension,
) -> Result<Option<Arc<dyn PhysicalExpr>>> {
    let Some(physical_expr_node::ExprType::Extension(node)) = &proto.expr_type else {
        return Ok(None);
    };
    if let Some(bytes) = node.expr.strip_prefix(CAST_PREFIX) {
        if bytes.len() > MAX_DESCRIPTOR {
            return Err(plan_datafusion_err!("cast field descriptor too large"));
        }
        let [input] = node.inputs.as_slice() else {
            return Err(plan_datafusion_err!(
                "metadata cast requires one cast input"
            ));
        };
        if !matches!(input.expr_type, Some(physical_expr_node::ExprType::Cast(_))) {
            return Err(plan_datafusion_err!("metadata cast input is not a cast"));
        }
        let decoded = converter.proto_to_physical_expr(input, schema, ctx)?;
        let cast = decoded
            .downcast_ref::<CastExpr>()
            .ok_or_else(|| plan_datafusion_err!("metadata cast input is not a cast"))?;
        let field = try_decode_field_ref(bytes)?;
        if field.data_type() != cast.cast_type() {
            return Err(plan_datafusion_err!("metadata cast type mismatch"));
        }
        return Ok(Some(Arc::new(CastExpr::new_with_target_field(
            Arc::clone(cast.expr()),
            field,
            Some(cast.cast_options().clone()),
        ))));
    }
    if let Some(bytes) = node.expr.strip_prefix(LITERAL_PREFIX) {
        if bytes.len() > MAX_DESCRIPTOR {
            return Err(plan_datafusion_err!("literal field descriptor too large"));
        }
        let [input] = node.inputs.as_slice() else {
            return Err(plan_datafusion_err!(
                "metadata literal requires one literal input"
            ));
        };
        if !matches!(
            input.expr_type,
            Some(physical_expr_node::ExprType::Literal(_))
        ) {
            return Err(plan_datafusion_err!(
                "metadata literal input is not a literal"
            ));
        }
        let value = converter.proto_to_physical_expr(input, schema, ctx)?;
        let literal = value
            .downcast_ref::<Literal>()
            .ok_or_else(|| plan_datafusion_err!("metadata literal input is not a literal"))?;
        let field = try_decode_field_ref(bytes)?;
        if field.data_type() != &literal.value().data_type() {
            return Err(plan_datafusion_err!("metadata literal type mismatch"));
        }
        let restored = Literal::new_with_metadata(
            literal.value().clone(),
            Some(FieldMetadata::new_from_field(&field)),
        );
        return Ok(Some(Arc::new(restored)));
    }
    let Some(bytes) = node.expr.strip_prefix(PREFIX) else {
        return Ok(None);
    };
    if bytes.len() > MAX_DESCRIPTOR {
        return Err(plan_datafusion_err!("native scalar descriptor too large"));
    }
    let descriptor: Descriptor = serde_json::from_slice(bytes)
        .map_err(|e| plan_datafusion_err!("native scalar descriptor: {e}"))?;
    // Match DataFusion's standard ScalarUdf decoder: an empty definition means
    // a function from the task registry (e.g. get_field), not an empty Sail UDF
    // descriptor. Native functions always carry their exact identity bytes.
    let udf = if descriptor.udf.is_empty() {
        ctx.task_ctx()
            .udf(&descriptor.name)
            .or_else(|_| ctx.codec().try_decode_udf(&descriptor.name, &[]))?
    } else {
        ctx.codec()
            .try_decode_udf(&descriptor.name, &descriptor.udf)?
    };
    let field = try_decode_field_ref(&descriptor.field)?;
    let args = node
        .inputs
        .iter()
        .map(|arg| converter.proto_to_physical_expr(arg, schema, ctx))
        .collect::<Result<_>>()?;
    Ok(Some(Arc::new(
        ScalarFunctionExpr::new(
            &descriptor.name,
            udf,
            args,
            field,
            Arc::clone(ctx.task_ctx().session_config().options()),
        )
        .with_nullable(descriptor.nullable),
    )))
}

#[cfg(test)]
mod tests {
    use datafusion::arrow::datatypes::{DataType, Field};
    use datafusion::execution::TaskContext;
    use datafusion::logical_expr::ScalarUDF;
    use datafusion::physical_expr::expressions::Column;
    use sail_common_datafusion::native_scalar::retain_scalar;

    use super::*;
    use crate::proto::{
        RemoteExecutionCodec, decode_remote_physical_expr, encode_remote_physical_expr,
    };

    #[test]
    fn native_scalar_expression_round_trip_preserves_full_return_field() -> Result<()> {
        let task = TaskContext::default();
        let udf = ScalarUDF::new_from_impl(OwnedScalar {
            name: "metadata_fixture".into(),
            identity: "fixture@1:metadata".into(),
            udf: (*datafusion::functions::math::abs()).clone(),
            owner: Arc::new(()),
        });
        retain_scalar(udf.clone())?;
        let field = Arc::new(
            Field::new("geometry", DataType::Float64, false).with_metadata(
                [
                    ("ARROW:extension:name".into(), "fixture.geometry".into()),
                    (
                        "ARROW:extension:metadata".into(),
                        "{\"crs\":\"EPSG:4326\"}".into(),
                    ),
                ]
                .into(),
            ),
        );
        let schema = Schema::new(vec![Field::new("x", DataType::Float64, false)]);
        let expr: Arc<dyn PhysicalExpr> = Arc::new(
            ScalarFunctionExpr::new(
                "metadata_fixture",
                Arc::new(udf),
                vec![Arc::new(Column::new("x", 0))],
                field.clone(),
                Arc::clone(task.session_config().options()),
            )
            .with_nullable(false),
        );
        let bytes = encode_remote_physical_expr(&RemoteExecutionCodec, &expr)?;
        let decoded = decode_remote_physical_expr(&task, &RemoteExecutionCodec, &bytes, &schema)?;
        assert_eq!(decoded.return_field(&schema)?, field);
        assert!(!decoded.nullable(&schema)?);
        assert_eq!(decoded.children().len(), 1);
        let literal: Arc<dyn PhysicalExpr> = Arc::new(Literal::new_with_metadata(
            datafusion::common::ScalarValue::Float64(Some(2.0)),
            Some(FieldMetadata::new_from_field(&field)),
        ));
        let bytes = encode_remote_physical_expr(&RemoteExecutionCodec, &literal)?;
        let decoded = decode_remote_physical_expr(&task, &RemoteExecutionCodec, &bytes, &schema)?;
        assert_eq!(
            decoded.return_field(&schema)?,
            literal.return_field(&schema)?
        );
        assert_eq!(
            decoded
                .downcast_ref::<Literal>()
                .ok_or_else(|| plan_datafusion_err!("expected restored literal"))?
                .value(),
            &datafusion::common::ScalarValue::Float64(Some(2.0))
        );
        Ok(())
    }

    #[test]
    fn builtin_geometry_and_explicit_cast_preserve_metadata_on_workers() -> Result<()> {
        use datafusion::logical_expr::ReturnFieldArgs;
        use sail_function::scalar::geo::st_geomfromwkb::StGeomFromWKB;

        let task = TaskContext::default();
        let schema = Schema::new(vec![Field::new("wkb", DataType::Binary, true)]);
        let udf = Arc::new(ScalarUDF::from(StGeomFromWKB::new()));
        let field = udf.return_field_from_args(ReturnFieldArgs {
            arg_fields: schema.fields(),
            scalar_arguments: &[None],
        })?;
        let scalar: Arc<dyn PhysicalExpr> = Arc::new(ScalarFunctionExpr::new(
            "st_geomfromwkb",
            udf,
            vec![Arc::new(Column::new("wkb", 0))],
            field.clone(),
            Arc::clone(task.session_config().options()),
        ));
        let cast: Arc<dyn PhysicalExpr> = Arc::new(CastExpr::new_with_target_field(
            Arc::new(Column::new("wkb", 0)),
            field.clone(),
            None,
        ));
        for original in [scalar, cast] {
            let bytes = encode_remote_physical_expr(&RemoteExecutionCodec, &original)?;
            let restored =
                decode_remote_physical_expr(&task, &RemoteExecutionCodec, &bytes, &schema)?;
            assert_eq!(
                restored.return_field(&schema)?,
                original.return_field(&schema)?
            );
            assert_eq!(restored.return_field(&schema)?.metadata(), field.metadata());
        }
        Ok(())
    }

    #[test]
    fn metadata_bearing_struct_access_uses_the_task_function_registry() -> Result<()> {
        let context = datafusion::prelude::SessionContext::new();
        let task = context.task_ctx();
        let field =
            Arc::new(Field::new("value", DataType::Utf8, true).with_metadata(
                [("description".into(), "ordinary property metadata".into())].into(),
            ));
        let schema = Schema::new(vec![Field::new(
            "node",
            DataType::Struct(vec![field.clone()].into()),
            true,
        )]);
        let expr: Arc<dyn PhysicalExpr> = Arc::new(ScalarFunctionExpr::new(
            "get_field",
            datafusion::functions::core::get_field(),
            vec![
                Arc::new(Column::new("node", 0)),
                Arc::new(Literal::new(datafusion::common::ScalarValue::Utf8(Some(
                    "value".into(),
                )))),
            ],
            field.clone(),
            Arc::clone(task.session_config().options()),
        ));
        let bytes = encode_remote_physical_expr(&RemoteExecutionCodec, &expr)?;
        let decoded = decode_remote_physical_expr(&task, &RemoteExecutionCodec, &bytes, &schema)?;
        assert_eq!(decoded.return_field(&schema)?, field);
        Ok(())
    }
}

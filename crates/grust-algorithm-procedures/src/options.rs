use super::*;
use algorithms::{MissingWeight, Orientation, PageRankOptions, ProjectionOptions, WeightSelection};

fn option(name: &str, value_type: ValueType, default: Value, nullable: bool) -> OptionField {
    OptionField {
        field: Field {
            name: name.into(),
            value_type,
            nullable,
        },
        default: Some(default),
    }
}

pub(super) fn projection_fields() -> Vec<OptionField> {
    vec![
        option(
            "orientation",
            ValueType::String,
            Value::String("outgoing".into()),
            false,
        ),
        option("nodeLabels", ValueType::Strings, Value::Null, true),
        option("relationshipTypes", ValueType::Strings, Value::Null, true),
        option("weightProperty", ValueType::String, Value::Null, true),
        option("defaultWeight", ValueType::Number, Value::Null, true),
    ]
}

pub(super) fn pagerank_fields() -> Vec<OptionField> {
    vec![
        option("damping", ValueType::Number, Value::Float(0.85), false),
        option("tolerance", ValueType::Number, Value::Float(1e-8), false),
        option("maxIterations", ValueType::Integer, Value::Int(1000), false),
        option("personalization", ValueType::Numbers, Value::Null, true),
    ]
}

fn value<'a>(args: &'a ValidatedArguments, key: &str) -> Result<&'a Value> {
    args.options()
        .get(key)
        .ok_or_else(|| ProcedureError::InvalidArguments(format!("missing normalized option {key}")))
}

fn number(value: &Value) -> Result<f64> {
    match value {
        Value::Float(value) if value.is_finite() => Ok(*value),
        Value::Int(value) if (-9_007_199_254_740_992..=9_007_199_254_740_992).contains(value) => {
            Ok(*value as f64)
        }
        _ => Err(ProcedureError::InvalidArguments(
            "numeric option must be in the exact f64 domain".into(),
        )),
    }
}

fn labels(value: &Value) -> Result<Option<&[String]>> {
    match value {
        Value::Null => Ok(None),
        Value::StringArray(values) => Ok(Some(values)),
        _ => Err(ProcedureError::InvalidArguments(
            "labels must be a string array".into(),
        )),
    }
}

pub(super) fn projection(args: &ValidatedArguments) -> Result<ProjectionOptions<'_>> {
    let orientation = match value(args, "orientation")? {
        Value::String(value) => match value.as_str() {
            "outgoing" => Orientation::Outgoing,
            "incoming" => Orientation::Incoming,
            "undirected" => Orientation::Undirected,
            _ => {
                return Err(ProcedureError::InvalidArguments(
                    "orientation must be outgoing, incoming or undirected".into(),
                ));
            }
        },
        _ => {
            return Err(ProcedureError::InvalidArguments(
                "orientation must be a string".into(),
            ));
        }
    };
    let missing = match value(args, "defaultWeight")? {
        Value::Null => MissingWeight::Reject,
        value => MissingWeight::Default(number(value)?),
    };
    let weight = match value(args, "weightProperty")? {
        Value::Null if missing == MissingWeight::Reject => WeightSelection::Unit,
        Value::String(key) => WeightSelection::Property { key, missing },
        _ => {
            return Err(ProcedureError::InvalidArguments(
                "defaultWeight requires weightProperty".into(),
            ));
        }
    };
    Ok(ProjectionOptions {
        node_labels: labels(value(args, "nodeLabels")?)?,
        relationship_labels: labels(value(args, "relationshipTypes")?)?,
        orientation,
        weight,
    })
}

pub(super) fn pagerank(args: &ValidatedArguments) -> Result<PageRankOptions<'_>> {
    let max_iterations = match value(args, "maxIterations")? {
        Value::Int(value) => usize::try_from(*value).map_err(|_| {
            ProcedureError::InvalidArguments("maxIterations must be positive".into())
        })?,
        _ => {
            return Err(ProcedureError::InvalidArguments(
                "maxIterations must be an integer".into(),
            ));
        }
    };
    let personalization = match value(args, "personalization")? {
        Value::Null => None,
        Value::FloatArray(values) => Some(values.as_slice()),
        _ => {
            return Err(ProcedureError::InvalidArguments(
                "personalization must be a numeric array".into(),
            ));
        }
    };
    Ok(PageRankOptions {
        damping: number(value(args, "damping")?)?,
        tolerance: number(value(args, "tolerance")?)?,
        max_iterations,
        personalization,
    })
}

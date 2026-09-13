//! Signature construction and dynamic argument normalization.

use std::collections::{BTreeMap, BTreeSet};

use grust_core::Value;

use crate::{ProcedureDefinition, ProcedureError, Result, ValidatedArguments, ValueType};

pub(super) fn validate_definition(definition: &ProcedureDefinition) -> Result<()> {
    for name in std::iter::once(&definition.name).chain(&definition.aliases) {
        if name.split('.').any(|segment| {
            segment.is_empty()
                || !segment.bytes().enumerate().all(|(index, byte)| {
                    byte.is_ascii_alphabetic() || byte == b'_' || index > 0 && byte.is_ascii_digit()
                })
        }) {
            return Err(ProcedureError::InvalidDefinition(format!(
                "invalid name: {name}"
            )));
        }
    }
    if definition.version == 0 || definition.provider.is_empty() {
        return Err(ProcedureError::InvalidDefinition(
            "version and provider must be specified".into(),
        ));
    }
    for fields in [
        definition
            .arguments
            .iter()
            .map(|arg| &arg.field)
            .collect::<Vec<_>>(),
        definition.options.iter().map(|opt| &opt.field).collect(),
        definition.outputs.iter().collect(),
    ] {
        let mut names = BTreeSet::new();
        for field in fields {
            if field.name.is_empty() || !names.insert(&field.name) {
                return Err(ProcedureError::InvalidDefinition(
                    "empty or duplicate field name".into(),
                ));
            }
        }
    }
    let mut optional = false;
    for arg in &definition.arguments {
        if let Some(value) = &arg.default {
            optional = true;
            if !arg.field.accepts(value) {
                return Err(ProcedureError::InvalidDefinition(format!(
                    "invalid default for {}",
                    arg.field.name
                )));
            }
        } else if optional {
            return Err(ProcedureError::InvalidDefinition(
                "required argument after optional argument".into(),
            ));
        }
    }
    for option in &definition.options {
        if option
            .default
            .as_ref()
            .is_some_and(|value| !option.field.accepts(value))
        {
            return Err(ProcedureError::InvalidDefinition(format!(
                "invalid default for {}",
                option.field.name
            )));
        }
    }
    match definition.options_argument {
        Some(index) => {
            if !definition
                .arguments
                .get(index)
                .is_some_and(|arg| arg.field.value_type == ValueType::Map && !arg.field.nullable)
            {
                return Err(ProcedureError::InvalidDefinition(
                    "options require a non-null map argument".into(),
                ));
            }
            if let Some(Value::Json(serde_json::Value::Object(defaults))) =
                &definition.arguments[index].default
            {
                validate_options(definition, defaults).map_err(|error| {
                    ProcedureError::InvalidDefinition(format!(
                        "invalid default option map: {error}"
                    ))
                })?;
            }
        }
        None if !definition.options.is_empty() => {
            return Err(ProcedureError::InvalidDefinition(
                "option schema without a map argument".into(),
            ));
        }
        None => {}
    }
    Ok(())
}

pub(super) fn validate_arguments(
    definition: &ProcedureDefinition,
    mut args: Vec<Value>,
) -> Result<ValidatedArguments> {
    args.try_reserve_exact(definition.arguments.len().saturating_sub(args.len()))?;
    for arg in definition.arguments.iter().skip(args.len()) {
        args.push(arg.default.clone().ok_or_else(|| {
            ProcedureError::InvalidArguments(format!("missing {}", arg.field.name))
        })?);
    }
    let mut options = BTreeMap::new();
    for (index, value) in args.iter_mut().enumerate() {
        if let Some(normalized) =
            normalize_array_argument(value, definition.arguments[index].field.value_type)?
        {
            *value = normalized;
        }
        if let Some(validated) = validate_argument(definition, index, value)? {
            options = validated;
        }
    }
    Ok(ValidatedArguments {
        positional: args,
        options,
        reservation: None,
    })
}

pub(super) fn argument_memory_bytes(definition: &ProcedureDefinition, args: &Vec<Value>) -> usize {
    let mut bytes = args
        .capacity()
        .max(definition.arguments.len())
        .saturating_mul(size_of::<Value>());
    for value in args.iter().chain(
        definition
            .arguments
            .iter()
            .skip(args.len())
            .filter_map(|argument| argument.default.as_ref()),
    ) {
        // Includes normalization scratch and the separately normalized options
        // map. Input ownership transfers to the provider with this reservation.
        bytes = bytes.saturating_add(value_payload_bytes(value).saturating_mul(4));
    }
    for option in &definition.options {
        bytes = bytes
            .saturating_add(2 * size_of::<(String, Value)>())
            .saturating_add(option.field.name.len());
        if let Some(value) = &option.default {
            bytes = bytes.saturating_add(value_payload_bytes(value).saturating_mul(4));
        }
    }
    bytes
}

pub(super) fn validate_argument(
    definition: &ProcedureDefinition,
    index: usize,
    value: &Value,
) -> Result<Option<BTreeMap<String, Value>>> {
    let arg = definition.arguments.get(index).ok_or_else(|| {
        ProcedureError::InvalidArguments("argument index outside signature".into())
    })?;
    let normalized = normalize_array_argument(value, arg.field.value_type)?;
    let value = normalized.as_ref().unwrap_or(value);
    if !arg.field.accepts(value) {
        return Err(ProcedureError::InvalidArguments(format!(
            "{} has wrong type or nullability",
            arg.field.name
        )));
    }
    if definition.options_argument == Some(index) {
        let Value::Json(serde_json::Value::Object(map)) = value else {
            return Err(ProcedureError::InvalidArguments(
                "options must be a map".into(),
            ));
        };
        Ok(Some(validate_options(definition, map)?))
    } else {
        Ok(None)
    }
}

fn normalize_array_argument(value: &Value, kind: crate::ValueType) -> Result<Option<Value>> {
    if matches!(
        kind,
        crate::ValueType::Strings | crate::ValueType::Integers | crate::ValueType::Numbers
    ) && let Value::Json(array @ serde_json::Value::Array(_)) = value
    {
        return declared_option_value(array, kind).map(Some);
    }
    if kind == crate::ValueType::Numbers
        && let Value::IntArray(values) = value
    {
        return values
            .iter()
            .map(|value| {
                if !(-9_007_199_254_740_992..=9_007_199_254_740_992).contains(value) {
                    return Err(ProcedureError::InvalidArguments(
                        "numeric array integer exceeds exact f64 domain".into(),
                    ));
                }
                Ok(*value as f64)
            })
            .collect::<Result<Vec<_>>>()
            .map(Value::FloatArray)
            .map(Some);
    }
    Ok(None)
}

fn validate_options(
    definition: &ProcedureDefinition,
    map: &serde_json::Map<String, serde_json::Value>,
) -> Result<BTreeMap<String, Value>> {
    let mut options = BTreeMap::new();
    for key in map.keys() {
        if !definition
            .options
            .iter()
            .any(|option| option.field.name == *key)
        {
            return Err(ProcedureError::UnknownOption(key.clone()));
        }
    }
    for option in &definition.options {
        let value = match map.get(&option.field.name) {
            Some(value) => declared_option_value(value, option.field.value_type)?,
            None => option.default.clone().ok_or_else(|| {
                ProcedureError::InvalidArguments(format!("missing option {}", option.field.name))
            })?,
        };
        if !option.field.accepts(&value) {
            return Err(ProcedureError::InvalidArguments(format!(
                "option {} has wrong type or nullability",
                option.field.name
            )));
        }
        options.insert(option.field.name.clone(), value);
    }
    Ok(options)
}

fn declared_option_value(value: &serde_json::Value, kind: crate::ValueType) -> Result<Value> {
    let serde_json::Value::Array(values) = value else {
        return Ok(Value::from_json(value.clone()));
    };
    // JSON has no typed empty arrays. The registered option schema supplies
    // that type; numeric arrays reject integer precision loss explicitly.
    let invalid = || {
        ProcedureError::InvalidArguments(
            "option array does not match its declared element type".into(),
        )
    };
    match kind {
        crate::ValueType::Strings => values
            .iter()
            .map(|value| value.as_str().map(str::to_owned).ok_or_else(invalid))
            .collect::<Result<Vec<_>>>()
            .map(Value::StringArray),
        crate::ValueType::Integers => values
            .iter()
            .map(|value| value.as_i64().ok_or_else(invalid))
            .collect::<Result<Vec<_>>>()
            .map(Value::IntArray),
        crate::ValueType::Numbers => values
            .iter()
            .map(|value| {
                if value.as_i64().is_some_and(|value| {
                    !(-9_007_199_254_740_992..=9_007_199_254_740_992).contains(&value)
                }) || value
                    .as_u64()
                    .is_some_and(|value| value > 9_007_199_254_740_992)
                {
                    return Err(invalid());
                }
                value
                    .as_f64()
                    .filter(|value| value.is_finite())
                    .ok_or_else(invalid)
            })
            .collect::<Result<Vec<_>>>()
            .map(Value::FloatArray),
        _ => Ok(Value::from_json(value.clone())),
    }
}

pub(super) fn value_payload_bytes(value: &Value) -> usize {
    match value {
        Value::Null
        | Value::Bool(_)
        | Value::Int(_)
        | Value::Float(_)
        | Value::Decimal(_)
        | Value::Duration(_) => 0,
        Value::String(value) => value.capacity(),
        Value::DateTime(value) => value.as_str().len(),
        Value::StringArray(values) => values.iter().fold(
            values.capacity().saturating_mul(size_of::<String>()),
            |bytes, value| bytes.saturating_add(value.capacity()),
        ),
        Value::IntArray(values) => values.capacity().saturating_mul(size_of::<i64>()),
        Value::FloatArray(values) => values.capacity().saturating_mul(size_of::<f64>()),
        Value::Json(value) => json_payload_bytes(value),
        Value::Path(path) => {
            json_array_bytes(&path.nodes).saturating_add(json_array_bytes(&path.relationships))
        }
        Value::Graph(graph) => {
            json_array_bytes(&graph.nodes).saturating_add(json_array_bytes(&graph.relationships))
        }
    }
}

fn json_array_bytes(values: &Vec<serde_json::Value>) -> usize {
    values.iter().fold(
        values
            .capacity()
            .saturating_mul(size_of::<serde_json::Value>()),
        |bytes, value| bytes.saturating_add(json_payload_bytes(value)),
    )
}

fn json_payload_bytes(value: &serde_json::Value) -> usize {
    match value {
        serde_json::Value::Null | serde_json::Value::Bool(_) | serde_json::Value::Number(_) => 0,
        serde_json::Value::String(value) => value.capacity(),
        serde_json::Value::Array(values) => json_array_bytes(values),
        serde_json::Value::Object(values) => values.iter().fold(0usize, |bytes, (key, value)| {
            // Conservative B-tree node overhead per entry; allocator overhead is
            // outside this cooperative estimate, as it is for other allocations.
            bytes
                .saturating_add(size_of::<(String, serde_json::Value)>() * 2)
                .saturating_add(key.capacity())
                .saturating_add(json_payload_bytes(value))
        }),
    }
}

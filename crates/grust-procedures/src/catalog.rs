//! Registry introspection bound to the same immutable generation as dispatch.

use crate::*;
use grust_core::Value;

pub(crate) fn definition() -> ProcedureDefinition {
    let outputs = [
        ("name", ValueType::String),
        ("aliases", ValueType::Strings),
        ("provider", ValueType::String),
        ("version", ValueType::Integer),
        ("mode", ValueType::String),
        ("inputs", ValueType::Strings),
        ("options", ValueType::Strings),
        ("outputs", ValueType::Strings),
        ("determinism", ValueType::String),
        ("correlation", ValueType::String),
        ("graph", ValueType::String),
        ("streaming", ValueType::String),
    ]
    .into_iter()
    .map(|(name, value_type)| Field {
        name: name.into(),
        value_type,
        nullable: false,
    })
    .collect();
    ProcedureDefinition {
        name: "db.procedures".into(),
        aliases: vec![],
        version: 1,
        provider: "grust.registry".into(),
        arguments: vec![],
        options_argument: None,
        options: vec![],
        outputs,
        mode: ProcedureMode::Catalog,
        determinism: Determinism::Deterministic,
        correlation: Correlation::Independent,
        graph: GraphRequirement::None,
        streaming: Streaming::Incremental,
    }
}

pub(crate) struct Catalog {
    rows: Vec<Vec<Value>>,
}

impl Catalog {
    pub(crate) fn new<'a>(definitions: impl Iterator<Item = &'a ProcedureDefinition>) -> Self {
        let rows = definitions
            .map(|definition| {
                vec![
                    Value::String(definition.name.clone()),
                    Value::StringArray(definition.aliases.clone()),
                    Value::String(definition.provider.clone()),
                    Value::Int(i64::from(definition.version)),
                    Value::String(format!("{:?}", definition.mode)),
                    Value::StringArray(
                        definition
                            .arguments
                            .iter()
                            .map(|argument| {
                                format!(
                                    "{} default={:?}",
                                    describe(&argument.field),
                                    argument.default
                                )
                            })
                            .collect(),
                    ),
                    Value::StringArray(
                        definition
                            .options
                            .iter()
                            .map(|option| {
                                format!("{} default={:?}", describe(&option.field), option.default)
                            })
                            .collect(),
                    ),
                    Value::StringArray(definition.outputs.iter().map(describe).collect()),
                    Value::String(format!("{:?}", definition.determinism)),
                    Value::String(format!("{:?}", definition.correlation)),
                    Value::String(format!("{:?}", definition.graph)),
                    Value::String(format!("{:?}", definition.streaming)),
                ]
            })
            .collect();
        Self { rows }
    }
}

fn describe(field: &Field) -> String {
    format!(
        "{}:{:?}{}",
        field.name,
        field.value_type,
        if field.nullable { "?" } else { "" }
    )
}

impl ProcedureProvider for Catalog {
    fn open<'a>(
        &'a self,
        _args: ValidatedArguments,
        invocation: Invocation<'a>,
    ) -> Result<Box<dyn ProcedureCursor + 'a>> {
        Ok(Box::new(Cursor {
            rows: self.rows.iter(),
            execution: invocation.execution,
        }))
    }
}

struct Cursor<'a> {
    rows: std::slice::Iter<'a, Vec<Value>>,
    execution: &'a ExecutionContext,
}
impl ProcedureCursor for Cursor<'_> {
    fn next_batch(&mut self) -> Result<Option<ProcedureBatch>> {
        self.execution.checkpoint()?;
        let Some(row) = self.rows.next() else {
            return Ok(None);
        };
        self.execution.charge_work(row.len())?;
        let reservation = self.execution.reserve(
            size_of::<Vec<Value>>().saturating_add(crate::registry::owned_row_bytes(row)),
        )?;
        let mut rows = Vec::new();
        rows.try_reserve_exact(1)?;
        rows.push(row.clone());
        Ok(Some(ProcedureBatch::new(rows, reservation)))
    }
}

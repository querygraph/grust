//! Standard catalog and table providers. Metadata is registered with its owner.

use std::collections::BTreeSet;
use std::sync::Arc;

use grust_core::Value;

use crate::{
    Argument, Correlation, Determinism, ExecutionContext, Field, GraphRequirement, Invocation,
    MemoryReservation, ProcedureBatch, ProcedureCursor, ProcedureDefinition, ProcedureError,
    ProcedureMode, ProcedureProvider, RegistryBuilder, Result, Streaming, ValidatedArguments,
    ValueType,
};

mod range;

/// Register the existing `db.*` catalog and `tvf.*` table procedures.
///
/// Registration rejects collisions rather than overriding application providers.
/// Catalog output is sorted and distinct. Range output is inclusive and ordered
/// by its step. Argument correlation remains the responsibility of the caller.
pub fn register_builtins(builder: &mut RegistryBuilder) -> Result<()> {
    range::register(builder)?;
    for (name, column, kind) in [
        ("db.labels", "label", CatalogKind::Labels),
        (
            "db.relationshipTypes",
            "relationshipType",
            CatalogKind::Relationships,
        ),
        ("db.propertyKeys", "propertyKey", CatalogKind::Properties),
    ] {
        builder.register(
            definition(name, column, ProcedureMode::Catalog),
            Arc::new(CatalogProvider(kind)),
        )?;
    }
    let mut keys = definition("tvf.keys", "key", ProcedureMode::Table);
    keys.arguments.push(Argument {
        field: Field {
            name: "element_or_map".into(),
            value_type: ValueType::Map,
            nullable: true,
        },
        default: None,
    });
    builder.register(keys, Arc::new(KeysProvider))?;
    builder.register_catalog()
}

fn definition(name: &str, column: &str, mode: ProcedureMode) -> ProcedureDefinition {
    ProcedureDefinition {
        name: name.into(),
        aliases: vec![],
        version: 1,
        provider: "grust.builtin".into(),
        arguments: vec![],
        options_argument: None,
        options: vec![],
        outputs: vec![Field {
            name: column.into(),
            value_type: ValueType::String,
            nullable: false,
        }],
        mode,
        determinism: Determinism::Deterministic,
        correlation: if mode == ProcedureMode::Catalog {
            Correlation::Independent
        } else {
            Correlation::PerRow
        },
        graph: if mode == ProcedureMode::Catalog {
            GraphRequirement::LocalSnapshot
        } else {
            GraphRequirement::None
        },
        streaming: Streaming::Blocking,
    }
}

enum CatalogKind {
    Labels,
    Relationships,
    Properties,
}
struct CatalogProvider(CatalogKind);

impl ProcedureProvider for CatalogProvider {
    fn open<'a>(
        &'a self,
        _args: ValidatedArguments,
        invocation: Invocation<'a>,
    ) -> Result<Box<dyn ProcedureCursor + 'a>> {
        let graph = invocation
            .snapshot
            .map(|snapshot| snapshot.graph())
            .ok_or_else(|| ProcedureError::Unsupported("catalog requires a local graph".into()))?;
        let execution = invocation.execution;
        // Two passes: account a conservative upper bound before allocating the
        // distinct set. No string/property cloning occurs during estimation.
        let visit = |consume: &mut dyn FnMut(&str) -> Result<()>| -> Result<()> {
            match self.0 {
                CatalogKind::Labels => {
                    for node in &graph.nodes {
                        execution.charge_work(1)?;
                        consume(node.label.as_str())?;
                    }
                }
                CatalogKind::Relationships => {
                    for edge in &graph.edges {
                        execution.charge_work(1)?;
                        consume(edge.label.as_str())?;
                    }
                }
                CatalogKind::Properties => {
                    for node in &graph.nodes {
                        execution.charge_work(1)?;
                        for key in node.props.keys() {
                            execution.charge_work(1)?;
                            consume(key)?;
                        }
                    }
                    for edge in &graph.edges {
                        execution.charge_work(1)?;
                        for key in edge.props.keys() {
                            execution.charge_work(1)?;
                            consume(key)?;
                        }
                    }
                }
            }
            Ok(())
        };
        let mut bytes = 0usize;
        visit(&mut |value| {
            bytes = bytes.saturating_add(string_set_entry_bytes(value));
            Ok(())
        })?;
        let scratch = execution.reserve(bytes)?;
        let mut values = BTreeSet::new();
        visit(&mut |value| {
            values.insert(value.to_owned());
            Ok(())
        })?;
        Ok(Box::new(StringCursor {
            values: values.into_iter(),
            execution,
            _scratch: scratch,
        }))
    }
}

struct KeysProvider;

impl ProcedureProvider for KeysProvider {
    fn open<'a>(
        &'a self,
        args: ValidatedArguments,
        invocation: Invocation<'a>,
    ) -> Result<Box<dyn ProcedureCursor + 'a>> {
        let execution = invocation.execution;
        let value = &args.positional()[0];
        let keys = match value {
            Value::Null => None,
            Value::Json(serde_json::Value::Object(map)) => {
                let props = match map.get("props") {
                    Some(serde_json::Value::Object(props)) => props,
                    _ => map,
                };
                Some(props.keys())
            }
            _ => {
                return Err(ProcedureError::InvalidArguments(
                    "keys expects a map or null".into(),
                ));
            }
        };
        let mut bytes = 0usize;
        if let Some(keys) = &keys {
            for key in keys.clone() {
                execution.charge_work(1)?;
                bytes = bytes.saturating_add(string_set_entry_bytes(key));
            }
        }
        let scratch = execution.reserve(bytes)?;
        let mut values = BTreeSet::new();
        if let Some(keys) = keys {
            for key in keys {
                execution.charge_work(1)?;
                values.insert(key.clone());
            }
        }
        Ok(Box::new(StringCursor {
            values: values.into_iter(),
            execution,
            _scratch: scratch,
        }))
    }
}

fn string_set_entry_bytes(value: &str) -> usize {
    // Includes conservative B-tree occupancy/pointers and the string buffer.
    (size_of::<String>() + 4 * size_of::<usize>())
        .saturating_mul(2)
        .saturating_add(value.len())
}

struct StringCursor<'a> {
    values: std::collections::btree_set::IntoIter<String>,
    execution: &'a ExecutionContext,
    _scratch: MemoryReservation,
}

impl ProcedureCursor for StringCursor<'_> {
    fn next_batch(&mut self) -> Result<Option<ProcedureBatch>> {
        if self.values.len() == 0 {
            return Ok(None);
        }
        // String length is not bounded by row count. One row per batch avoids
        // extra lookahead ownership and admits a single oversized value explicitly.
        self.execution.charge_work(1)?;
        let value = self.values.next().ok_or_else(|| {
            ProcedureError::OutputContract("catalog iterator length changed".into())
        })?;
        let bytes = size_of::<Vec<Value>>()
            .saturating_add(size_of::<Value>())
            .saturating_add(value.capacity());
        let reservation = self.execution.reserve(bytes)?;
        let mut row = Vec::new();
        row.try_reserve_exact(1)?;
        row.push(Value::String(value));
        let mut rows = Vec::new();
        rows.try_reserve_exact(1)?;
        rows.push(row);
        Ok(Some(ProcedureBatch::new(rows, reservation)))
    }
}

//! An application provider registered without editing the parser or executor.
use grust_core::{Graph, Value};
use grust_cypher::{CypherParameters, procedures::*, run_read_query_with_registry};
use std::sync::Arc;

struct Double;
struct Cursor(Option<ProcedureBatch>);

impl ProcedureProvider for Double {
    fn open<'a>(
        &'a self,
        args: ValidatedArguments,
        invocation: Invocation<'a>,
    ) -> Result<Box<dyn ProcedureCursor + 'a>> {
        let [Value::Int(input)] = args.positional() else {
            return Err(ProcedureError::InvalidArguments(
                "expected an integer".into(),
            ));
        };
        let output = input
            .checked_mul(2)
            .ok_or_else(|| ProcedureError::Numerical("double overflow".into()))?;
        invocation.execution.charge_work(1)?;
        let reservation = invocation
            .execution
            .reserve(size_of::<Vec<Value>>() + size_of::<Value>())?;
        let mut row = Vec::new();
        row.try_reserve_exact(1)?;
        row.push(Value::Int(output));
        let mut rows = Vec::new();
        rows.try_reserve_exact(1)?;
        rows.push(row);
        Ok(Box::new(Cursor(Some(ProcedureBatch::new(
            rows,
            reservation,
        )))))
    }
}
impl ProcedureCursor for Cursor {
    fn next_batch(&mut self) -> Result<Option<ProcedureBatch>> {
        Ok(self.0.take())
    }
}

fn main() -> std::result::Result<(), Box<dyn std::error::Error>> {
    let mut registry = RegistryBuilder::default();
    register_builtins(&mut registry)?;
    registry.register(
        ProcedureDefinition {
            name: "example.double".into(),
            aliases: vec![],
            version: 1,
            provider: "application".into(),
            arguments: vec![Argument {
                field: Field {
                    name: "input".into(),
                    value_type: ValueType::Integer,
                    nullable: false,
                },
                default: None,
            }],
            options_argument: None,
            options: vec![],
            outputs: vec![Field {
                name: "value".into(),
                value_type: ValueType::Integer,
                nullable: false,
            }],
            mode: ProcedureMode::Table,
            determinism: Determinism::Deterministic,
            correlation: Correlation::PerRow,
            graph: GraphRequirement::None,
            streaming: Streaming::Incremental,
        },
        Arc::new(Double),
    )?;
    let result = run_read_query_with_registry(
        &Graph::default(),
        "default",
        "UNWIND [3, 7] AS input CALL example.double(input) YIELD value AS doubled RETURN input, doubled",
        &CypherParameters::new(),
        &registry.build(),
    )?;
    assert_eq!(
        result.rows,
        vec![
            vec![Value::Int(3), Value::Int(6)],
            vec![Value::Int(7), Value::Int(14)]
        ]
    );
    println!("{:?}", result.rows);
    Ok(())
}

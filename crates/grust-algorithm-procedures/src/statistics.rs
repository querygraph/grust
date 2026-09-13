//! Read-only projection inspection and explicitly limited sizing procedures.

use super::*;

pub(super) fn register(builder: &mut RegistryBuilder) -> Result<()> {
    for (name, outputs, provider) in [
        (
            "projectionStats",
            vec!["nodes", "edges", "arcs", "selfLoops", "csrBytes"],
            inspect as Inspect,
        ),
        (
            "estimateCsr",
            vec![
                "nodesUpperBound",
                "edgesUpperBound",
                "maxArcs",
                "outgoingCsrBytes",
                "reverseCsrBytes",
                "positionsBytes",
            ],
            estimate as Inspect,
        ),
    ] {
        builder.register(
            ProcedureDefinition {
                name: format!("grust.algorithms.{name}"),
                aliases: vec![],
                version: 1,
                provider: "grust.algorithms".into(),
                arguments: vec![Argument {
                    field: field("configuration", ValueType::Map),
                    default: Some(Value::Json(serde_json::json!({}))),
                }],
                options_argument: Some(0),
                options: options::projection_fields(),
                outputs: outputs
                    .into_iter()
                    .map(|name| field(name, ValueType::Integer))
                    .collect(),
                mode: ProcedureMode::Read,
                determinism: Determinism::Deterministic,
                correlation: Correlation::PerRow,
                graph: GraphRequirement::LocalSnapshot,
                streaming: Streaming::Blocking,
            },
            Arc::new(Provider(provider)),
        )?;
    }
    Ok(())
}

type Inspect = fn(&ValidatedArguments, &Invocation<'_>) -> Result<ProcedureBatch>;
struct Provider(Inspect);
struct Cursor(Option<ProcedureBatch>);

impl ProcedureProvider for Provider {
    fn open<'a>(
        &'a self,
        args: ValidatedArguments,
        invocation: Invocation<'a>,
    ) -> Result<Box<dyn ProcedureCursor + 'a>> {
        Ok(Box::new(Cursor(Some((self.0)(&args, &invocation)?))))
    }
}

impl ProcedureCursor for Cursor {
    fn next_batch(&mut self) -> Result<Option<ProcedureBatch>> {
        Ok(self.0.take())
    }
}

fn inspect(args: &ValidatedArguments, invocation: &Invocation<'_>) -> Result<ProcedureBatch> {
    let snapshot = snapshot(invocation)?;
    let graph = preparation::prepare(snapshot, options::projection(args)?, invocation)?;
    let stats = graph.statistics()?;
    row(
        &[
            stats.nodes,
            stats.edges,
            stats.arcs,
            stats.self_loops,
            stats.csr_bytes,
        ],
        invocation.execution,
    )
}

fn estimate(args: &ValidatedArguments, invocation: &Invocation<'_>) -> Result<ProcedureBatch> {
    let snapshot = snapshot(invocation)?;
    let options = options::projection(args)?;
    let nodes = snapshot.graph().nodes.len();
    let edges = snapshot.graph().edges.len();
    let estimate = algorithms::CsrEstimate::upper_bound(
        nodes,
        edges,
        options.orientation,
        matches!(options.weight, algorithms::WeightSelection::Property { .. }),
    )?;
    row(
        &[
            nodes,
            edges,
            estimate.max_arcs,
            estimate.outgoing_bytes,
            estimate.reverse_bytes,
            estimate.positions_bytes,
        ],
        invocation.execution,
    )
}

fn snapshot<'a>(invocation: &Invocation<'a>) -> Result<LocalSnapshot<'a>> {
    invocation.snapshot.ok_or_else(|| {
        ProcedureError::Unsupported("inspection requires an admitted local snapshot".into())
    })
}

fn row(values: &[usize], context: &ExecutionContext) -> Result<ProcedureBatch> {
    context.charge_work(values.len())?;
    let reservation =
        context.reserve(size_of::<Vec<Value>>() + values.len() * size_of::<Value>())?;
    let mut row = Vec::new();
    row.try_reserve_exact(values.len())?;
    for &value in values {
        row.push(Value::Int(i64::try_from(value).map_err(|_| {
            ProcedureError::Numerical("inspection output exceeds Cypher integer domain".into())
        })?));
    }
    let mut rows = Vec::new();
    rows.try_reserve_exact(1)?;
    rows.push(row);
    Ok(ProcedureBatch::new(rows, reservation))
}

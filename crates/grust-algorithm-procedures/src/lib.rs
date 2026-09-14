//! Algorithm providers for the ordinary parser-independent procedure registry.
//! Kernels live in grust-algorithms; this crate only selects, invokes and adapts.

use grust_algorithms as algorithms;
use grust_core::Value;
use grust_procedures::*;
use std::sync::Arc;

mod options;
mod output;
mod preparation;
mod statistics;
use output::{AlgorithmCursor, AlgorithmOutput};

/// Register the initial read-only algorithm catalog. No parser changes or
/// hardcoded name dispatcher are needed when applications register more providers.
pub fn register_algorithms(builder: &mut RegistryBuilder) -> Result<()> {
    statistics::register(builder)?;
    register(
        builder,
        "degree",
        None,
        vec![
            field("nodeId", ValueType::String),
            field("degree", ValueType::Integer),
            nullable("strength", ValueType::Number),
        ],
        vec![],
        |graph, _| Ok(AlgorithmOutput::Degrees(algorithms::degree(graph)?)),
    )?;
    register(
        builder,
        "bfs",
        Some(ValueType::String),
        vec![
            field("nodeId", ValueType::String),
            nullable("distance", ValueType::Number),
        ],
        vec![],
        |graph, args| {
            Ok(AlgorithmOutput::Distances(algorithms::bfs(
                graph,
                source(args)?,
            )?))
        },
    )?;
    register(
        builder,
        "dijkstra",
        Some(ValueType::String),
        vec![
            field("nodeId", ValueType::String),
            nullable("distance", ValueType::Number),
        ],
        vec![],
        |graph, args| {
            Ok(AlgorithmOutput::Distances(algorithms::dijkstra(
                graph,
                source(args)?,
            )?))
        },
    )?;
    register(
        builder,
        "shortestPaths",
        Some(ValueType::String),
        vec![
            field("sourceNodeId", ValueType::String),
            field("targetNodeId", ValueType::String),
            field("totalCost", ValueType::Number),
            field("nodeIds", ValueType::Strings),
            field("costs", ValueType::Numbers),
            field("edgeOrdinals", ValueType::Integers),
        ],
        vec![],
        |graph, args| {
            Ok(AlgorithmOutput::Paths(
                algorithms::shortest_paths(graph, source(args)?)?.into_cursor()?,
            ))
        },
    )?;
    register(
        builder,
        "wcc",
        None,
        vec![
            field("nodeId", ValueType::String),
            field("componentId", ValueType::String),
        ],
        vec![],
        |graph, _| {
            Ok(AlgorithmOutput::Components(
                algorithms::weakly_connected_components(graph)?,
            ))
        },
    )?;
    register(
        builder,
        "scc",
        None,
        vec![
            field("nodeId", ValueType::String),
            field("componentId", ValueType::String),
        ],
        vec![],
        |graph, _| {
            Ok(AlgorithmOutput::Components(
                algorithms::strongly_connected_components(graph)?,
            ))
        },
    )?;
    register(
        builder,
        "pagerank",
        None,
        vec![
            field("nodeId", ValueType::String),
            field("score", ValueType::Number),
            field("iterations", ValueType::Integer),
            field("converged", ValueType::Boolean),
            field("residual", ValueType::Number),
        ],
        options::pagerank_fields(),
        |graph, args| {
            Ok(AlgorithmOutput::PageRank(algorithms::pagerank(
                graph,
                options::pagerank(args)?,
            )?))
        },
    )?;
    register(
        builder,
        "dfs",
        Some(ValueType::String),
        vec![
            field("nodeId", ValueType::String),
            field("visitIndex", ValueType::Integer),
        ],
        vec![],
        |graph, args| {
            Ok(AlgorithmOutput::Order(algorithms::depth_first(
                graph,
                source(args)?,
            )?))
        },
    )?;
    register(
        builder,
        "multiSourceBfs",
        Some(ValueType::Strings),
        vec![
            field("nodeId", ValueType::String),
            nullable("distance", ValueType::Number),
        ],
        vec![],
        |graph, args| {
            let Some(Value::StringArray(sources)) = args.positional().first() else {
                return Err(ProcedureError::InvalidArguments(
                    "sources must be an array of external IDs".into(),
                ));
            };
            Ok(AlgorithmOutput::Distances(algorithms::multi_source_bfs(
                graph, sources,
            )?))
        },
    )?;
    register(
        builder,
        "topologicalSort",
        None,
        vec![
            field("acyclic", ValueType::Boolean),
            field("nodeIds", ValueType::Strings),
            field("cycleNodeIds", ValueType::Strings),
        ],
        vec![],
        |graph, _| {
            Ok(AlgorithmOutput::Topology(algorithms::topological_sort(
                graph,
            )?))
        },
    )
}

fn field(name: &str, value_type: ValueType) -> Field {
    Field {
        name: name.into(),
        value_type,
        nullable: false,
    }
}
fn nullable(name: &str, value_type: ValueType) -> Field {
    Field {
        nullable: true,
        ..field(name, value_type)
    }
}

type Kernel = fn(&algorithms::GraphProjection, &ValidatedArguments) -> Result<AlgorithmOutput>;
struct Provider {
    kernel: Kernel,
}

fn register(
    builder: &mut RegistryBuilder,
    name: &str,
    source: Option<ValueType>,
    outputs: Vec<Field>,
    extra_options: Vec<OptionField>,
    kernel: Kernel,
) -> Result<()> {
    let mut arguments = Vec::new();
    if let Some(source_type) = source {
        arguments.push(Argument {
            field: field(
                if source_type == ValueType::Strings {
                    "sources"
                } else {
                    "source"
                },
                source_type,
            ),
            default: None,
        });
    }
    let options_argument = arguments.len();
    arguments.push(Argument {
        field: field("configuration", ValueType::Map),
        default: Some(Value::Json(serde_json::json!({}))),
    });
    let mut options = options::projection_fields();
    options.extend(extra_options);
    builder.register(
        ProcedureDefinition {
            name: format!("grust.algorithms.{name}"),
            aliases: vec![],
            version: 1,
            provider: "grust.algorithms".into(),
            arguments,
            options_argument: Some(options_argument),
            options,
            outputs,
            mode: ProcedureMode::Read,
            determinism: Determinism::Deterministic,
            correlation: Correlation::PerRow,
            graph: GraphRequirement::LocalSnapshot,
            streaming: Streaming::Blocking,
        },
        Arc::new(Provider { kernel }),
    )
}

impl ProcedureProvider for Provider {
    fn open<'a>(
        &'a self,
        args: ValidatedArguments,
        invocation: Invocation<'a>,
    ) -> Result<Box<dyn ProcedureCursor + 'a>> {
        let snapshot = invocation.snapshot.ok_or_else(|| {
            ProcedureError::Unsupported("algorithm requires an admitted local snapshot".into())
        })?;
        let graph = preparation::prepare(snapshot, options::projection(&args)?, &invocation)?;
        let output = (self.kernel)(&graph, &args)?;
        Ok(Box::new(AlgorithmCursor::new(graph, output)))
    }
}

fn source(args: &ValidatedArguments) -> Result<&str> {
    match args.positional().first() {
        Some(Value::String(source)) => Ok(source),
        _ => Err(ProcedureError::InvalidArguments(
            "source must be an external node ID string".into(),
        )),
    }
}

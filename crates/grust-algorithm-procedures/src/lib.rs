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
    for spec in catalog() {
        register(builder, spec)?;
    }
    Ok(())
}

/// Every projection kernel, once: registration and direct execution both read
/// this list, so a kernel cannot be registered without being runnable.
fn catalog() -> Vec<Spec> {
    let mut specs = Vec::new();
    specs.push(Spec::new(
        "degree",
        None,
        vec![
            field("nodeId", ValueType::String),
            field("degree", ValueType::Integer),
            nullable("strength", ValueType::Number),
        ],
        vec![],
        |graph, _| Ok(AlgorithmOutput::Degrees(algorithms::degree(graph)?)),
    ));
    specs.push(Spec::new(
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
    ));
    specs.push(Spec::new(
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
    ));
    specs.push(Spec::new(
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
            Ok(AlgorithmOutput::Paths(algorithms::shortest_paths(
                graph,
                source(args)?,
            )?))
        },
    ));
    specs.push(Spec::new(
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
    ));
    specs.push(Spec::new(
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
    ));
    specs.push(Spec::new(
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
    ));
    specs.push(Spec::new(
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
    ));
    specs.push(Spec::new(
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
    ));
    specs.push(Spec::new(
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
    ));
    specs.push(Spec::new(
        "kCore",
        None,
        vec![
            field("nodeId", ValueType::String),
            field("coreValue", ValueType::Integer),
            field("degeneracy", ValueType::Integer),
        ],
        vec![],
        |graph, _| {
            Ok(AlgorithmOutput::Table(
                algorithms::k_core(graph)?.into_table(),
            ))
        },
    ));
    specs.push(Spec::new(
        "triangleCount",
        None,
        vec![
            field("nodeId", ValueType::String),
            field("triangles", ValueType::Integer),
            field("triangleCount", ValueType::Integer),
        ],
        options::triangle_fields(),
        |graph, args| {
            Ok(AlgorithmOutput::Table(
                algorithms::triangles(graph, options::triangles(args)?)?.into_triangle_table()?,
            ))
        },
    ));
    specs.push(Spec::new(
        "localClusteringCoefficient",
        None,
        vec![
            field("nodeId", ValueType::String),
            nullable("coefficient", ValueType::Number),
            field("triangles", ValueType::Integer),
            field("averageCoefficient", ValueType::Number),
        ],
        options::triangle_fields(),
        |graph, args| {
            Ok(AlgorithmOutput::Table(
                algorithms::triangles(graph, options::triangles(args)?)?
                    .into_coefficient_table()?,
            ))
        },
    ));
    specs.push(Spec::new(
        "betweenness",
        None,
        vec![
            field("nodeId", ValueType::String),
            field("score", ValueType::Number),
        ],
        options::betweenness_fields(),
        |graph, args| {
            Ok(AlgorithmOutput::Table(
                algorithms::betweenness(graph, options::betweenness(args)?)?.into_table()?,
            ))
        },
    ));
    specs.push(Spec::new(
        "closeness",
        None,
        vec![
            field("nodeId", ValueType::String),
            field("score", ValueType::Number),
        ],
        options::closeness_fields(),
        |graph, args| {
            Ok(AlgorithmOutput::Table(
                algorithms::closeness(graph, options::closeness(args)?)?.into_table()?,
            ))
        },
    ));
    specs.push(Spec::new(
        "harmonic",
        None,
        vec![
            field("nodeId", ValueType::String),
            field("score", ValueType::Number),
        ],
        options::harmonic_fields(),
        |graph, args| {
            Ok(AlgorithmOutput::Table(
                algorithms::harmonic(graph, options::harmonic(args)?)?.into_table()?,
            ))
        },
    ));
    specs.push(Spec::new(
        "labelPropagation",
        None,
        vec![
            field("nodeId", ValueType::String),
            field("communityId", ValueType::String),
            field("iterations", ValueType::Integer),
            field("converged", ValueType::Boolean),
        ],
        options::label_propagation_fields(),
        |graph, args| {
            Ok(AlgorithmOutput::Table(
                algorithms::label_propagation(graph, options::label_propagation(args)?)?
                    .into_table()?,
            ))
        },
    ));
    specs.push(Spec::new(
        "nodeSimilarity",
        None,
        vec![
            field("node1", ValueType::String),
            field("node2", ValueType::String),
            field("similarity", ValueType::Number),
        ],
        options::node_similarity_fields(),
        |graph, args| {
            Ok(AlgorithmOutput::Table(
                algorithms::node_similarity(graph, options::node_similarity(args)?)?
                    .into_table()?,
            ))
        },
    ));
    specs.push(Spec::new(
        "bridges",
        None,
        vec![
            field("sourceNodeId", ValueType::String),
            field("targetNodeId", ValueType::String),
            field("edgeOrdinal", ValueType::Integer),
        ],
        vec![],
        |graph, _| {
            Ok(AlgorithmOutput::Table(
                algorithms::biconnectivity(graph)?.into_bridge_table()?,
            ))
        },
    ));
    specs.push(Spec::new(
        "articulationPoints",
        None,
        vec![field("nodeId", ValueType::String)],
        vec![],
        |graph, _| {
            Ok(AlgorithmOutput::Table(
                algorithms::biconnectivity(graph)?.into_articulation_table()?,
            ))
        },
    ));
    specs.push(Spec::new(
        "biconnectedComponents",
        None,
        vec![
            field("sourceNodeId", ValueType::String),
            field("targetNodeId", ValueType::String),
            field("edgeOrdinal", ValueType::Integer),
            field("componentId", ValueType::Integer),
        ],
        vec![],
        |graph, _| {
            Ok(AlgorithmOutput::Table(
                algorithms::biconnectivity(graph)?.into_component_table()?,
            ))
        },
    ));
    specs.push(Spec::new(
        "spanningTree",
        None,
        vec![
            field("sourceNodeId", ValueType::String),
            field("targetNodeId", ValueType::String),
            field("edgeOrdinal", ValueType::Integer),
            field("weight", ValueType::Number),
            field("totalWeight", ValueType::Number),
        ],
        options::spanning_tree_fields(),
        |graph, args| {
            Ok(AlgorithmOutput::Table(
                algorithms::spanning_tree(graph, options::spanning_tree(args)?)?.into_table()?,
            ))
        },
    ));
    specs.push(Spec::new(
        "eigenvector",
        None,
        vec![
            field("nodeId", ValueType::String),
            field("score", ValueType::Number),
            field("iterations", ValueType::Integer),
            field("converged", ValueType::Boolean),
            field("residual", ValueType::Number),
        ],
        options::iteration_fields(),
        |graph, args| {
            Ok(AlgorithmOutput::Table(
                algorithms::eigenvector(graph, options::iteration(args)?)?.into_table()?,
            ))
        },
    ));
    specs.push(Spec::new(
        "katz",
        None,
        vec![
            field("nodeId", ValueType::String),
            field("score", ValueType::Number),
            field("iterations", ValueType::Integer),
            field("converged", ValueType::Boolean),
            field("residual", ValueType::Number),
        ],
        options::katz_fields(),
        |graph, args| {
            Ok(AlgorithmOutput::Table(
                algorithms::katz(graph, options::katz(args)?)?.into_table()?,
            ))
        },
    ));
    specs.push(Spec::new(
        "hits",
        None,
        vec![
            field("nodeId", ValueType::String),
            field("hub", ValueType::Number),
            field("authority", ValueType::Number),
            field("iterations", ValueType::Integer),
            field("converged", ValueType::Boolean),
            field("residual", ValueType::Number),
        ],
        options::iteration_fields(),
        |graph, args| {
            Ok(AlgorithmOutput::Table(
                algorithms::hits(graph, options::iteration(args)?)?.into_table()?,
            ))
        },
    ));
    specs.push(Spec::new(
        "leiden",
        None,
        vec![
            field("nodeId", ValueType::String),
            field("communityId", ValueType::String),
            field("modularity", ValueType::Number),
            field("levels", ValueType::Integer),
            field("converged", ValueType::Boolean),
        ],
        options::louvain_fields(),
        |graph, args| {
            Ok(AlgorithmOutput::Table(
                algorithms::leiden(graph, options::louvain(args)?)?.into_table()?,
            ))
        },
    ));
    specs.push(Spec::new(
        "louvain",
        None,
        vec![
            field("nodeId", ValueType::String),
            field("communityId", ValueType::String),
            field("modularity", ValueType::Number),
            field("levels", ValueType::Integer),
            field("converged", ValueType::Boolean),
        ],
        options::louvain_fields(),
        |graph, args| {
            Ok(AlgorithmOutput::Table(
                algorithms::louvain(graph, options::louvain(args)?)?.into_table()?,
            ))
        },
    ));
    specs
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

struct Spec {
    name: &'static str,
    source: Option<ValueType>,
    outputs: Vec<Field>,
    extra_options: Vec<OptionField>,
    kernel: Kernel,
}

impl Spec {
    fn new(
        name: &'static str,
        source: Option<ValueType>,
        outputs: Vec<Field>,
        extra_options: Vec<OptionField>,
        kernel: Kernel,
    ) -> Self {
        Self {
            name,
            source,
            outputs,
            extra_options,
            kernel,
        }
    }
}

const PREFIX: &str = "grust.algorithms.";

/// The projection options a validated call carries: orientation, label and
/// relationship-type selection, and the weight property with its default. A
/// caller that builds its own `GraphProjection` reads them with this, so its
/// projection means what the registered procedure's would.
pub fn projection_options(args: &ValidatedArguments) -> Result<algorithms::ProjectionOptions<'_>> {
    options::projection(args)
}

/// Run a registered kernel on a projection the caller already holds, and hand
/// back its typed Arrow results. `name` is the registered name, in any ASCII
/// case, with or without the `grust.algorithms.` prefix. `args` must have been validated against that
/// procedure's definition, exactly as the registry validates a `CALL`.
///
/// `projectionStats` and `estimateCsr` are not kernels over a projection: one
/// reads projection metadata and the other sizes a graph before it is built.
/// They are refused here; call `GraphProjection::statistics` or
/// `CsrEstimate::upper_bound`.
#[cfg(feature = "arrow")]
pub fn run_on_projection(
    name: &str,
    graph: &algorithms::GraphProjection,
    args: &ValidatedArguments,
) -> Result<algorithms::ArrowResultCursor> {
    let short = name.strip_prefix(PREFIX).unwrap_or(name);
    let spec = catalog()
        .into_iter()
        .find(|spec| spec.name.eq_ignore_ascii_case(short))
        .ok_or_else(|| {
            ProcedureError::Unsupported(format!("`{name}` is not a registered projection kernel"))
        })?;
    (spec.kernel)(graph, args)?.into_arrow_results()
}

/// Names `run_on_projection` serves, without the prefix, in registration order.
pub fn projection_kernel_names() -> Vec<&'static str> {
    catalog().into_iter().map(|spec| spec.name).collect()
}

fn register(builder: &mut RegistryBuilder, spec: Spec) -> Result<()> {
    let Spec {
        name,
        source,
        outputs,
        extra_options,
        kernel,
    } = spec;
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
            name: format!("{PREFIX}{name}"),
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
        Ok(Box::new(AlgorithmCursor::new(graph, output)?))
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

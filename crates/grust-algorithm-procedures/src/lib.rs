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
    // Streamed, never an n×n matrix: the cursor runs one source at a time.
    specs.push(Spec::new(
        "allPairsShortestPaths",
        None,
        vec![
            field("sourceNodeId", ValueType::String),
            field("targetNodeId", ValueType::String),
            field("distance", ValueType::Number),
        ],
        options::all_pairs_fields(),
        |graph, args| {
            Ok(AlgorithmOutput::AllPairs(
                algorithms::all_pairs_shortest_paths(graph, options::all_pairs(args)?)?,
            ))
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
    // ArticleRank is PageRank's recurrence with a damped divisor, so it is the
    // same kernel, the same options and the same result shape.
    specs.push(Spec::new(
        "articleRank",
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
                options::article_rank(args)?,
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
    // The community ids come from a node property, so these are the first
    // kernels the registry serves with `NodeProperties`.
    const COMMUNITY: &[PropertyOption] = &[PropertyOption {
        option: "communityProperty",
        kind: algorithms::PropertyKind::Integer,
        missing: algorithms::MissingProperty::Reject,
        needed: always,
    }];
    specs.push(Spec::with_properties(
        "modularity",
        vec![
            field("nodeId", ValueType::String),
            field("communityId", ValueType::Integer),
            field("size", ValueType::Integer),
            field("modularity", ValueType::Number),
            nullable("conductance", ValueType::Number),
            field("totalModularity", ValueType::Number),
        ],
        options::community_quality_fields(),
        COMMUNITY,
        |properties, args| {
            let key = community_key(args)?;
            Ok(AlgorithmOutput::Table(
                algorithms::community_quality(properties, key, options::resolution(args)?)?
                    .into_table()?,
            ))
        },
    ));
    // The heuristic is great-circle distance, so the two coordinate columns are
    // node properties and the kernel is served through the property path.
    const COORDINATES: &[PropertyOption] = &[
        PropertyOption {
            option: "latitudeProperty",
            kind: algorithms::PropertyKind::Number,
            missing: algorithms::MissingProperty::Reject,
            needed: always,
        },
        PropertyOption {
            option: "longitudeProperty",
            kind: algorithms::PropertyKind::Number,
            missing: algorithms::MissingProperty::Reject,
            needed: always,
        },
    ];
    specs.push(
        Spec::with_properties(
            "astar",
            vec![
                field("nodeId", ValueType::String),
                field("costFromSource", ValueType::Number),
                field("edgeOrdinal", ValueType::Integer),
                field("totalCost", ValueType::Number),
                field("settled", ValueType::Integer),
            ],
            options::astar_fields(),
            COORDINATES,
            |properties, args| {
                let (latitude, longitude) = astar_coordinates(args)?;
                Ok(AlgorithmOutput::Table(
                    algorithms::astar_haversine(
                        properties,
                        source(args)?,
                        target(args)?,
                        latitude,
                        longitude,
                    )?
                    .into_table()?,
                ))
            },
        )
        .with_source_and_target(),
    );
    specs.push(
        Spec::new(
            "yens",
            Some(ValueType::String),
            vec![
                field("sourceNodeId", ValueType::String),
                field("targetNodeId", ValueType::String),
                field("totalCost", ValueType::Number),
                field("nodeIds", ValueType::Strings),
                field("costs", ValueType::Numbers),
                field("edgeOrdinals", ValueType::Integers),
                field("pathIndex", ValueType::Integer),
            ],
            options::yens_fields(),
            |graph, args| {
                Ok(AlgorithmOutput::RankedPaths(algorithms::yens(
                    graph,
                    source(args)?,
                    target(args)?,
                    options::yens(args)?,
                )?))
            },
        )
        .with_target(),
    );
    specs.push(
        Spec::new(
            "bellmanFord",
            Some(ValueType::String),
            vec![
                field("nodeId", ValueType::String),
                nullable("distance", ValueType::Number),
                field("cycleIndex", ValueType::Integer),
                field("negativeCycle", ValueType::Boolean),
            ],
            vec![],
            |graph, args| {
                Ok(AlgorithmOutput::Table(
                    algorithms::bellman_ford(graph, source(args)?)?.into_table()?,
                ))
            },
        )
        .with_signed_weights(),
    );
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
    // Only `sameCommunity` reads a property, so the community is requested for
    // that metric alone: the other five run on a graph without community ids,
    // and through `run_on_projection`, which supplies no properties.
    const LINK_COMMUNITY: &[PropertyOption] = &[PropertyOption {
        option: "communityProperty",
        kind: algorithms::PropertyKind::Integer,
        missing: algorithms::MissingProperty::Reject,
        needed: |args| Ok(options::link_metric(args)? == algorithms::LinkMetric::SameCommunity),
    }];
    specs.push(Spec::with_properties(
        "linkPrediction",
        vec![
            field("node1", ValueType::String),
            field("node2", ValueType::String),
            field("score", ValueType::Number),
        ],
        options::link_prediction_fields(),
        LINK_COMMUNITY,
        |properties, args| {
            let graph = properties.projection();
            let metric = options::link_metric(args)?;
            let pairs = options::link_pairs(args)?
                .map(|(first, second)| algorithms::CandidatePairs::from_ids(graph, first, second))
                .transpose()?;
            let candidates = pairs
                .as_ref()
                .map_or(algorithms::LinkCandidates::DistanceTwo, |pairs| {
                    algorithms::LinkCandidates::Pairs(pairs)
                });
            let communities = if metric == algorithms::LinkMetric::SameCommunity {
                Some((properties, community_key(args)?))
            } else {
                None
            };
            Ok(AlgorithmOutput::Table(
                algorithms::link_prediction(
                    graph,
                    algorithms::LinkPredictionOptions {
                        metric,
                        candidates,
                        communities,
                    },
                )?
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
    specs.push(
        Spec::new(
            "maxFlow",
            Some(ValueType::String),
            vec![
                field("sourceNodeId", ValueType::String),
                field("targetNodeId", ValueType::String),
                field("edgeOrdinal", ValueType::Integer),
                field("flow", ValueType::Number),
                field("maxFlow", ValueType::Number),
            ],
            vec![],
            |graph, args| {
                Ok(AlgorithmOutput::Table(
                    algorithms::max_flow(graph, source(args)?, target(args)?)?.into_flow_table()?,
                ))
            },
        )
        .with_target(),
    );
    specs.push(
        Spec::new(
            "minCut",
            Some(ValueType::String),
            vec![
                field("nodeId", ValueType::String),
                field("sourceSide", ValueType::Boolean),
                field("maxFlow", ValueType::Number),
            ],
            vec![],
            |graph, args| {
                Ok(AlgorithmOutput::Table(
                    algorithms::max_flow(graph, source(args)?, target(args)?)?.into_cut_table()?,
                ))
            },
        )
        .with_target(),
    );
    specs.push(Spec::new(
        "fastRP",
        None,
        vec![
            field("nodeId", ValueType::String),
            field("embedding", ValueType::Numbers),
        ],
        options::fast_rp_fields(),
        |graph, args| {
            Ok(AlgorithmOutput::Table(
                algorithms::fast_rp(graph, options::fast_rp(args)?)?.into_table()?,
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
/// A kernel that also reads node properties. The projection is reachable as
/// `properties.projection()`, so it is not passed twice.
type PropertyKernel =
    fn(&algorithms::NodeProperties, &ValidatedArguments) -> Result<AlgorithmOutput>;

enum Body {
    Topology(Kernel),
    WithProperties {
        kernel: PropertyKernel,
        /// Which options name node properties, and how to read them.
        properties: &'static [PropertyOption],
    },
}

/// An option whose value is the name of a node property the kernel reads.
#[derive(Clone, Copy)]
/// One option through which a kernel names a node property it reads.
///
/// Declared by the kernel, so it is known before any call: see
/// [`node_property_options`].
pub struct PropertyOption {
    /// The option's name, as the caller writes it.
    pub option: &'static str,
    /// The kind of column the kernel reads through it.
    pub kind: algorithms::PropertyKind,
    /// What the kernel does where the value is absent.
    pub missing: algorithms::MissingProperty,
    /// Whether this call reads it: a kernel may need a property for some of
    /// its options only. Private so the declaration's shape stays the
    /// kernel's; an embedder asks through [`PropertyOption::needed`].
    needed: fn(&ValidatedArguments) -> Result<bool>,
}

impl PropertyOption {
    /// Whether a call with these arguments reads this property. Most options
    /// are read by every call; `linkPrediction`'s `communityProperty` is read
    /// only when `metric` is `sameCommunity`. An embedder staging columns
    /// before it has a call can stage every declared option; one that has
    /// validated arguments can skip the options this returns `false` for.
    pub fn needed(&self, args: &ValidatedArguments) -> Result<bool> {
        (self.needed)(args)
    }
}

fn always(_: &ValidatedArguments) -> Result<bool> {
    Ok(true)
}

/// Read the property names a call asks for, in declaration order.
fn requests<'a>(
    declared: &'static [PropertyOption],
    args: &'a ValidatedArguments,
) -> Result<Vec<algorithms::PropertyRequest<'a>>> {
    let mut wanted = Vec::new();
    wanted.try_reserve_exact(declared.len())?;
    for declaration in declared {
        if !(declaration.needed)(args)? {
            continue;
        }
        let Some(Value::String(key)) = args.options().get(declaration.option) else {
            return Err(ProcedureError::InvalidArguments(format!(
                "{} must name a node property",
                declaration.option
            )));
        };
        wanted.push(algorithms::PropertyRequest {
            key,
            kind: declaration.kind,
            missing: declaration.missing,
        });
    }
    Ok(wanted)
}

struct Provider {
    body: Body,
    signed: bool,
}

struct Spec {
    name: &'static str,
    source: Option<ValueType>,
    /// A second positional node id, `target`, after `source`.
    target: bool,
    /// The kernel handles negative weights, so its projection admits them.
    signed: bool,
    outputs: Vec<Field>,
    extra_options: Vec<OptionField>,
    body: Body,
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
            target: false,
            signed: false,
            outputs,
            extra_options,
            body: Body::Topology(kernel),
        }
    }

    /// A kernel that reads node properties named by `properties`.
    fn with_properties(
        name: &'static str,
        outputs: Vec<Field>,
        extra_options: Vec<OptionField>,
        properties: &'static [PropertyOption],
        kernel: PropertyKernel,
    ) -> Self {
        Self {
            name,
            source: None,
            target: false,
            outputs,
            extra_options,
            body: Body::WithProperties { kernel, properties },
            // A kernel that reads node properties still gets the ordinary,
            // nonnegative weights; only `bellmanFord` asks for signed ones.
            signed: false,
        }
    }
}

impl Spec {
    fn with_target(mut self) -> Self {
        self.target = true;
        self
    }

    /// A property kernel that also takes `source` and `target` positionally.
    fn with_source_and_target(mut self) -> Self {
        self.source = Some(ValueType::String);
        self.target = true;
        self
    }

    fn with_signed_weights(mut self) -> Self {
        self.signed = true;
        self
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

/// As [`projection_options`], for the kernel that will run on the projection.
/// The difference is weights: a kernel that handles negative ones, `bellmanFord`,
/// gets a projection that admits them, and every other kernel gets one that
/// refuses them when it is built, which is where a caller wants to hear of it.
/// `name` is matched as [`run_on_projection`] matches it.
pub fn projection_options_for<'a>(
    name: &str,
    args: &'a ValidatedArguments,
) -> Result<algorithms::ProjectionOptions<'a>> {
    let wanted = short_name(name);
    let signed = catalog()
        .iter()
        .any(|spec| spec.signed && spec.name.eq_ignore_ascii_case(wanted));
    Ok(admit_signed(options::projection(args)?, signed))
}

/// A kernel's name without the `grust.algorithms.` prefix, which, like the name,
/// is matched whatever its case: the registry resolves names that way.
/// The node property a community call names.
fn community_key(args: &ValidatedArguments) -> Result<&str> {
    match args.options().get("communityProperty") {
        Some(Value::String(key)) => Ok(key),
        _ => Err(ProcedureError::InvalidArguments(
            "communityProperty must name a node property".into(),
        )),
    }
}

/// The two coordinate properties an A* call names.
fn astar_coordinates(args: &ValidatedArguments) -> Result<(&str, &str)> {
    let read = |key: &str| match args.options().get(key) {
        Some(Value::String(value)) => Ok(value.as_str()),
        _ => Err(ProcedureError::InvalidArguments(format!(
            "{key} must name a node property"
        ))),
    };
    Ok((read("latitudeProperty")?, read("longitudeProperty")?))
}

fn short_name(name: &str) -> &str {
    match name.get(..PREFIX.len()) {
        Some(prefix) if prefix.eq_ignore_ascii_case(PREFIX) => &name[PREFIX.len()..],
        _ => name,
    }
}

fn admit_signed(
    mut options: algorithms::ProjectionOptions<'_>,
    signed: bool,
) -> algorithms::ProjectionOptions<'_> {
    if signed && let algorithms::WeightSelection::Property { key, missing } = options.weight {
        options.weight = algorithms::WeightSelection::SignedProperty { key, missing };
    }
    options
}

/// Run a registered kernel on a projection the caller already holds, and hand
/// back its typed Arrow results. `name` is the registered name, in any ASCII
/// case, with or without the `grust.algorithms.` prefix. `args` must have been validated against that
/// procedure's definition, exactly as the registry validates a `CALL`.
///
/// `projectionStats` and `estimateCsr` are not kernels over a projection: one
/// reads projection metadata and the other sizes a graph before it is built.
/// They are refused here; call `GraphProjection::statistics` or
/// `CsrEstimate::upper_bound`. A kernel that reads node properties for this
/// call is refused too, and names itself: the caller must supply them, through
/// [`node_property_requests`] and [`run_with_properties`]. One that reads none
/// with these options (`linkPrediction` other than `sameCommunity`) runs.
#[cfg(feature = "arrow")]
pub fn run_on_projection(
    name: &str,
    graph: &algorithms::GraphProjection,
    args: &ValidatedArguments,
) -> Result<algorithms::ArrowResultCursor> {
    let short = short_name(name);
    let spec = catalog()
        .into_iter()
        .find(|spec| spec.name.eq_ignore_ascii_case(short))
        .ok_or_else(|| {
            ProcedureError::Unsupported(format!("`{name}` is not a registered projection kernel"))
        })?;
    match spec.body {
        Body::Topology(kernel) => kernel(graph, args)?.into_arrow_results(),
        Body::WithProperties { kernel, properties } => {
            if requests(properties, args)?.is_empty() {
                return kernel(&algorithms::NodeProperties::empty(graph), args)?
                    .into_arrow_results();
            }
            Err(ProcedureError::Unsupported(format!(
                "`{name}` reads node properties; build them with node_property_requests and call run_with_properties"
            )))
        }
    }
}

/// The options through which `name` names the node properties it reads, as the
/// kernel declares them. Empty for a kernel that reads none.
///
/// This is readable before any call exists. [`node_property_requests`] answers
/// for one validated call, and validation fills an absent option from its
/// default — `astar` reads `latitude` and `longitude` unless told otherwise —
/// so the requests always name *some* column. What a caller cannot learn from
/// them without first building arguments is which options exist and what
/// kind of column each must be. An embedder that constructs its own graph, such
/// as one probing a kernel's result schema, asks here, stages a column of the
/// declared kind per option, and names those columns in the options it
/// validates. Otherwise the defaults name columns its graph does not have, and
/// a property declared [`MissingProperty::Reject`](algorithms::MissingProperty)
/// refuses the call.
///
/// An option is listed even where only some calls read it, such as
/// `linkPrediction`'s `communityProperty`; [`PropertyOption::needed`] answers
/// for one call's validated arguments.
pub fn node_property_options(name: &str) -> Result<&'static [PropertyOption]> {
    let short = short_name(name);
    let spec = catalog()
        .into_iter()
        .find(|spec| spec.name.eq_ignore_ascii_case(short))
        .ok_or_else(|| {
            ProcedureError::Unsupported(format!("`{name}` is not a registered projection kernel"))
        })?;
    Ok(match spec.body {
        Body::Topology(_) => &[],
        Body::WithProperties { properties, .. } => properties,
    })
}

/// The node properties `name` reads for this call: the property keys the
/// caller's options name, each with the kind and missing-value policy the
/// kernel declared. Empty for a kernel that reads none.
///
/// An embedder that stages its own columns asks with this and supplies them to
/// [`run_with_properties`]. [`node_property_options`] is how a caller learns
/// which options exist, and of what kind, before it has a call to ask about.
pub fn node_property_requests<'a>(
    name: &str,
    args: &'a ValidatedArguments,
) -> Result<Vec<algorithms::PropertyRequest<'a>>> {
    let short = short_name(name);
    let spec = catalog()
        .into_iter()
        .find(|spec| spec.name.eq_ignore_ascii_case(short))
        .ok_or_else(|| {
            ProcedureError::Unsupported(format!("`{name}` is not a registered projection kernel"))
        })?;
    match spec.body {
        Body::Topology(_) => Ok(Vec::new()),
        Body::WithProperties { properties, .. } => requests(properties, args),
    }
}

/// As [`run_on_projection`], for a kernel that reads node properties. The
/// projection is `properties.projection()`. A kernel that reads none runs here
/// too, ignoring them, so an embedder may use one path for every name.
#[cfg(feature = "arrow")]
pub fn run_with_properties(
    name: &str,
    properties: &algorithms::NodeProperties,
    args: &ValidatedArguments,
) -> Result<algorithms::ArrowResultCursor> {
    let short = short_name(name);
    let spec = catalog()
        .into_iter()
        .find(|spec| spec.name.eq_ignore_ascii_case(short))
        .ok_or_else(|| {
            ProcedureError::Unsupported(format!("`{name}` is not a registered projection kernel"))
        })?;
    match spec.body {
        Body::Topology(kernel) => kernel(properties.projection(), args)?.into_arrow_results(),
        Body::WithProperties { kernel, .. } => kernel(properties, args)?.into_arrow_results(),
    }
}

/// Names `run_on_projection` serves, without the prefix, in registration order.
pub fn projection_kernel_names() -> Vec<&'static str> {
    catalog().into_iter().map(|spec| spec.name).collect()
}

fn register(builder: &mut RegistryBuilder, spec: Spec) -> Result<()> {
    let Spec {
        name,
        source,
        target,
        signed,
        outputs,
        extra_options,
        body,
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
    if target {
        arguments.push(Argument {
            field: field("target", ValueType::String),
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
        Arc::new(Provider { body, signed }),
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
        let options = admit_signed(options::projection(&args)?, self.signed);
        let graph = preparation::prepare(snapshot, options, &invocation)?;
        let output = match &self.body {
            Body::Topology(kernel) => kernel(&graph, &args)?,
            Body::WithProperties { kernel, properties } => {
                let wanted = requests(properties, &args)?;
                let read =
                    algorithms::NodeProperties::from_graph(snapshot.graph(), &graph, &wanted)?;
                kernel(&read, &args)?
            }
        };
        Ok(Box::new(AlgorithmCursor::new(graph, output)?))
    }
}

fn target(args: &ValidatedArguments) -> Result<&str> {
    match args.positional().get(1) {
        Some(Value::String(target)) => Ok(target),
        _ => Err(ProcedureError::InvalidArguments(
            "target must be an external node ID string".into(),
        )),
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

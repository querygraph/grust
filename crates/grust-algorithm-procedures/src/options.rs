use super::*;
use algorithms::{
    BetweennessOptions, ClosenessOptions, FastRpOptions, HarmonicOptions, IterationOptions,
    KatzOptions, LabelPropagationOptions, LouvainOptions, MissingWeight, NodeSimilarityOptions,
    Orientation, PageRankOptions, ProjectionOptions, RankVariant, SimilarityMetric,
    SpanningObjective, SpanningTreeOptions, TriangleOptions, WeightSelection,
};

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
    rank(args, RankVariant::PageRank)
}

/// The same options, for the ArticleRank variant.
pub(super) fn article_rank(args: &ValidatedArguments) -> Result<PageRankOptions<'_>> {
    rank(args, RankVariant::ArticleRank)
}

fn rank(args: &ValidatedArguments, variant: RankVariant) -> Result<PageRankOptions<'_>> {
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
        variant,
        damping: number(value(args, "damping")?)?,
        tolerance: number(value(args, "tolerance")?)?,
        max_iterations,
        personalization,
    })
}

pub(super) fn triangle_fields() -> Vec<OptionField> {
    vec![option("maxDegree", ValueType::Integer, Value::Null, true)]
}

pub(super) fn triangles(args: &ValidatedArguments) -> Result<TriangleOptions> {
    let max_degree = match value(args, "maxDegree")? {
        Value::Null => None,
        Value::Int(value) => Some(usize::try_from(*value).map_err(|_| {
            ProcedureError::InvalidArguments("maxDegree must not be negative".into())
        })?),
        _ => {
            return Err(ProcedureError::InvalidArguments(
                "maxDegree must be an integer".into(),
            ));
        }
    };
    Ok(TriangleOptions { max_degree })
}

pub(super) fn louvain_fields() -> Vec<OptionField> {
    vec![
        option("resolution", ValueType::Number, Value::Float(1.0), false),
        option("maxLevels", ValueType::Integer, Value::Int(10), false),
        option("maxIterations", ValueType::Integer, Value::Int(10), false),
        option("tolerance", ValueType::Number, Value::Float(1e-4), false),
        option("seed", ValueType::Integer, Value::Null, true),
    ]
}

fn positive(args: &ValidatedArguments, key: &str) -> Result<usize> {
    match value(args, key)? {
        Value::Int(value) if *value > 0 => usize::try_from(*value)
            .map_err(|_| ProcedureError::InvalidArguments(format!("{key} is too large"))),
        _ => Err(ProcedureError::InvalidArguments(format!(
            "{key} must be a positive integer"
        ))),
    }
}

/// `null` is no seed; any integer is one, and its bits are what matter.
fn seed(args: &ValidatedArguments) -> Result<Option<u64>> {
    match value(args, "seed")? {
        Value::Null => Ok(None),
        Value::Int(value) => Ok(Some(*value as u64)),
        _ => Err(ProcedureError::InvalidArguments(
            "seed must be an integer".into(),
        )),
    }
}

pub(super) fn betweenness_fields() -> Vec<OptionField> {
    vec![
        option("samplingSize", ValueType::Integer, Value::Null, true),
        option("seed", ValueType::Integer, Value::Null, true),
        option("normalized", ValueType::Boolean, Value::Bool(false), false),
    ]
}

pub(super) fn betweenness(args: &ValidatedArguments) -> Result<BetweennessOptions> {
    Ok(BetweennessOptions {
        sampling_size: match value(args, "samplingSize")? {
            Value::Null => None,
            _ => Some(positive(args, "samplingSize")?),
        },
        seed: seed(args)?.unwrap_or(0),
        normalized: matches!(value(args, "normalized")?, Value::Bool(true)),
    })
}

pub(super) fn closeness_fields() -> Vec<OptionField> {
    vec![option(
        "useWassermanFaust",
        ValueType::Boolean,
        Value::Bool(false),
        false,
    )]
}

pub(super) fn closeness(args: &ValidatedArguments) -> Result<ClosenessOptions> {
    Ok(ClosenessOptions {
        wasserman_faust: matches!(value(args, "useWassermanFaust")?, Value::Bool(true)),
    })
}

pub(super) fn harmonic_fields() -> Vec<OptionField> {
    vec![option(
        "normalized",
        ValueType::Boolean,
        Value::Bool(true),
        false,
    )]
}

pub(super) fn harmonic(args: &ValidatedArguments) -> Result<HarmonicOptions> {
    Ok(HarmonicOptions {
        normalized: matches!(value(args, "normalized")?, Value::Bool(true)),
    })
}

pub(super) fn label_propagation_fields() -> Vec<OptionField> {
    vec![
        option("maxIterations", ValueType::Integer, Value::Int(10), false),
        option("seed", ValueType::Integer, Value::Null, true),
    ]
}

pub(super) fn label_propagation(args: &ValidatedArguments) -> Result<LabelPropagationOptions> {
    Ok(LabelPropagationOptions {
        max_iterations: positive(args, "maxIterations")?,
        seed: seed(args)?,
    })
}

pub(super) fn node_similarity_fields() -> Vec<OptionField> {
    vec![
        option(
            "metric",
            ValueType::String,
            Value::String("jaccard".into()),
            false,
        ),
        option("topK", ValueType::Integer, Value::Int(10), false),
        option("topN", ValueType::Integer, Value::Int(0), false),
        option(
            "similarityCutoff",
            ValueType::Number,
            Value::Float(0.0),
            false,
        ),
        option("degreeCutoff", ValueType::Integer, Value::Int(1), false),
        option("upperDegreeCutoff", ValueType::Integer, Value::Null, true),
    ]
}

pub(super) fn node_similarity(args: &ValidatedArguments) -> Result<NodeSimilarityOptions> {
    let metric = match value(args, "metric")? {
        Value::String(value) => match value.to_ascii_lowercase().as_str() {
            "jaccard" => SimilarityMetric::Jaccard,
            "overlap" => SimilarityMetric::Overlap,
            "cosine" => SimilarityMetric::Cosine,
            _ => {
                return Err(ProcedureError::InvalidArguments(
                    "metric must be jaccard, overlap or cosine".into(),
                ));
            }
        },
        _ => {
            return Err(ProcedureError::InvalidArguments(
                "metric must be a string".into(),
            ));
        }
    };
    let top_n = match value(args, "topN")? {
        Value::Int(0) => 0,
        _ => positive(args, "topN")?,
    };
    Ok(NodeSimilarityOptions {
        metric,
        top_k: positive(args, "topK")?,
        top_n,
        similarity_cutoff: number(value(args, "similarityCutoff")?)?,
        degree_cutoff: positive(args, "degreeCutoff")?,
        upper_degree_cutoff: match value(args, "upperDegreeCutoff")? {
            Value::Null => None,
            _ => Some(positive(args, "upperDegreeCutoff")?),
        },
    })
}

pub(super) fn spanning_tree_fields() -> Vec<OptionField> {
    vec![
        option(
            "objective",
            ValueType::String,
            Value::String("minimum".into()),
            false,
        ),
        option("sourceNode", ValueType::String, Value::Null, true),
    ]
}

pub(super) fn spanning_tree(args: &ValidatedArguments) -> Result<SpanningTreeOptions<'_>> {
    let objective = match value(args, "objective")? {
        Value::String(value) => match value.to_ascii_lowercase().as_str() {
            "minimum" => SpanningObjective::Minimum,
            "maximum" => SpanningObjective::Maximum,
            _ => {
                return Err(ProcedureError::InvalidArguments(
                    "objective must be minimum or maximum".into(),
                ));
            }
        },
        _ => {
            return Err(ProcedureError::InvalidArguments(
                "objective must be a string".into(),
            ));
        }
    };
    let source = match value(args, "sourceNode")? {
        Value::Null => None,
        Value::String(id) => Some(id.as_str()),
        _ => {
            return Err(ProcedureError::InvalidArguments(
                "sourceNode must be a node id".into(),
            ));
        }
    };
    Ok(SpanningTreeOptions { objective, source })
}

pub(super) fn iteration_fields() -> Vec<OptionField> {
    vec![
        option("tolerance", ValueType::Number, Value::Float(1e-8), false),
        option("maxIterations", ValueType::Integer, Value::Int(1000), false),
    ]
}

pub(super) fn iteration(args: &ValidatedArguments) -> Result<IterationOptions> {
    Ok(IterationOptions {
        tolerance: number(value(args, "tolerance")?)?,
        max_iterations: positive(args, "maxIterations")?,
    })
}

pub(super) fn katz_fields() -> Vec<OptionField> {
    let mut fields = vec![
        option("alpha", ValueType::Number, Value::Float(0.1), false),
        option("beta", ValueType::Number, Value::Float(1.0), false),
        option("normalized", ValueType::Boolean, Value::Bool(false), false),
    ];
    fields.extend(iteration_fields());
    fields
}

pub(super) fn katz(args: &ValidatedArguments) -> Result<KatzOptions> {
    Ok(KatzOptions {
        alpha: number(value(args, "alpha")?)?,
        beta: number(value(args, "beta")?)?,
        normalized: matches!(value(args, "normalized")?, Value::Bool(true)),
        iteration: iteration(args)?,
    })
}

pub(super) fn fast_rp_fields() -> Vec<OptionField> {
    vec![
        option(
            "embeddingDimension",
            ValueType::Integer,
            Value::Int(128),
            false,
        ),
        option(
            "iterationWeights",
            ValueType::Numbers,
            Value::FloatArray(vec![0.0, 1.0, 1.0]),
            false,
        ),
        option(
            "nodeSelfInfluence",
            ValueType::Number,
            Value::Float(0.0),
            false,
        ),
        option(
            "normalizationStrength",
            ValueType::Number,
            Value::Float(0.0),
            false,
        ),
        option("seed", ValueType::Integer, Value::Null, true),
    ]
}

pub(super) fn fast_rp(args: &ValidatedArguments) -> Result<FastRpOptions<'_>> {
    let iteration_weights = match value(args, "iterationWeights")? {
        Value::FloatArray(values) => values.as_slice(),
        _ => {
            return Err(ProcedureError::InvalidArguments(
                "iterationWeights must be a numeric array".into(),
            ));
        }
    };
    Ok(FastRpOptions {
        dimension: positive(args, "embeddingDimension")?,
        iteration_weights,
        self_influence: number(value(args, "nodeSelfInfluence")?)?,
        normalization_strength: number(value(args, "normalizationStrength")?)?,
        seed: seed(args)?.unwrap_or(0),
    })
}

pub(super) fn louvain(args: &ValidatedArguments) -> Result<LouvainOptions> {
    let seed = seed(args)?;
    Ok(LouvainOptions {
        resolution: number(value(args, "resolution")?)?,
        max_levels: positive(args, "maxLevels")?,
        max_iterations: positive(args, "maxIterations")?,
        tolerance: number(value(args, "tolerance")?)?,
        seed,
    })
}

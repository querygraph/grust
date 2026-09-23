//! Link prediction: a score per node pair for how likely an edge between them
//! is, from what surrounds the two nodes.
//!
//! The six metrics are NetworKit's `linkprediction` indices (via icebug, MIT):
//! `CommonNeighborsIndex`, `AdamicAdarIndex`, `ResourceAllocationIndex`,
//! `PreferentialAttachmentIndex`, `TotalNeighborsIndex` and
//! `SameCommunityIndex`; candidates at distance two are its
//! `MissingLinksFinder::findAtDistance(2)`.

use crate::{
    AlgorithmError, GraphProjection, NodeProperties, Orientation, Result,
    buffer::Buffer,
    table::{NodeColumn, NodeTable},
};
use grust_procedures::{ExecutionContext, WorkMeter};

/// How a pair is scored. `N(x)` is the set of `x`'s distinct neighbours,
/// itself excluded, and `|N(x)|` its size.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum LinkMetric {
    /// `|N(u) ∩ N(v)|` (Newman 2001).
    #[default]
    CommonNeighbors,
    /// `Σ_{w ∈ N(u) ∩ N(v)} 1 / ln |N(w)|` (Adamic and Adar 2003): a shared
    /// neighbour counts for less the more neighbours it has.
    AdamicAdar,
    /// `Σ_{w ∈ N(u) ∩ N(v)} 1 / |N(w)|` (Zhou, Lü and Zhang 2009).
    ResourceAllocation,
    /// `|N(u)| · |N(v)|` (Barabási and Albert 1999).
    PreferentialAttachment,
    /// `|N(u) ∪ N(v)|`.
    TotalNeighbors,
    /// `1` when the two nodes carry the same community id, else `0`.
    SameCommunity,
}

/// Which pairs to score.
#[derive(Clone, Copy, Default)]
pub enum LinkCandidates<'a> {
    /// Every unordered pair `{u, v}` of nodes that are not adjacent and share
    /// at least one neighbour, which on an undirected graph is every pair at
    /// distance exactly two. Emitted once each, `node1 < node2` by projection
    /// row, ordered by `node1` then `node2`. The number of such pairs is bounded
    /// by `Σ_w |N(w)|²`, which a hub makes large; every step is charged.
    #[default]
    DistanceTwo,
    /// Exactly these pairs, in this order, duplicates and adjacent pairs
    /// included: row `i` of the result scores pair `i`.
    Pairs(&'a CandidatePairs),
}

/// Candidate pairs, resolved to projection rows and admitted.
pub struct CandidatePairs {
    graph: GraphProjection,
    first: Buffer<usize>,
    second: Buffer<usize>,
}

impl CandidatePairs {
    /// Pairs of projection rows. A row outside the projection is rejected.
    pub fn from_rows(graph: &GraphProjection, pairs: &[(usize, usize)]) -> Result<Self> {
        let context = graph.execution();
        context.charge_work(pairs.len())?;
        let n = graph.node_count();
        let mut first = Buffer::capacity(pairs.len(), context)?;
        let mut second = Buffer::capacity(pairs.len(), context)?;
        for &(a, b) in pairs {
            if a >= n || b >= n {
                return Err(invalid(format!(
                    "candidate pair ({a}, {b}) names a row outside the projection's {n}"
                )));
            }
            first.values.push(a);
            second.values.push(b);
        }
        Ok(Self {
            graph: graph.clone(),
            first,
            second,
        })
    }

    /// Pairs `(first[i], second[i])` of external node ids. The two lists must
    /// have the same length, and every id must be a projected node.
    pub fn from_ids<A: AsRef<str>, B: AsRef<str>>(
        graph: &GraphProjection,
        first: &[A],
        second: &[B],
    ) -> Result<Self> {
        if first.len() != second.len() {
            return Err(invalid(format!(
                "candidate lists differ in length: {} and {}",
                first.len(),
                second.len()
            )));
        }
        let context = graph.execution();
        let mut pairs = Pairs::new(graph, first.len())?;
        let mut meter = context.work_meter();
        for (a, b) in first.iter().zip(second) {
            meter.charge(1)?;
            pairs.push(a.as_ref(), b.as_ref())?;
        }
        Ok(pairs.finish())
    }

    /// Pairs from the Utf8 columns `first` and `second` of `batches`, in batch
    /// order. Nulls and ids outside the projection are rejected.
    #[cfg(feature = "arrow")]
    pub fn from_arrow_batches(
        graph: &GraphProjection,
        batches: &[arrow_array::RecordBatch],
        first: &str,
        second: &str,
    ) -> Result<Self> {
        use arrow_array::{Array, StringArray};
        let column = |batch: &'_ arrow_array::RecordBatch, name: &str| -> Result<StringArray> {
            batch
                .column_by_name(name)
                .and_then(|column| column.as_any().downcast_ref::<StringArray>())
                .cloned()
                .ok_or_else(|| {
                    AlgorithmError::Unsupported(format!(
                        "Arrow column {name} must exist with Utf8 type"
                    ))
                })
        };
        let total = batches
            .iter()
            .try_fold(0usize, |sum, batch| sum.checked_add(batch.num_rows()))
            .ok_or_else(|| AlgorithmError::Numerical("Arrow row count overflow".into()))?;
        let context = graph.execution();
        let mut pairs = Pairs::new(graph, total)?;
        let mut meter = context.work_meter();
        for batch in batches {
            let (a, b) = (column(batch, first)?, column(batch, second)?);
            for row in 0..batch.num_rows() {
                meter.charge(1)?;
                if a.is_null(row) || b.is_null(row) {
                    return Err(invalid(format!(
                        "Arrow columns {first} and {second} must not contain null"
                    )));
                }
                pairs.push(a.value(row), b.value(row))?;
            }
        }
        Ok(pairs.finish())
    }

    /// Number of pairs.
    pub fn len(&self) -> usize {
        self.first.values.len()
    }
    /// Whether there are none.
    pub fn is_empty(&self) -> bool {
        self.first.values.is_empty()
    }
    /// First node of each pair, as a projection row.
    pub fn first(&self) -> &[usize] {
        &self.first.values
    }
    /// Second node of each pair, as a projection row.
    pub fn second(&self) -> &[usize] {
        &self.second.values
    }
}

/// Resolves ids into admitted row buffers.
struct Pairs<'a> {
    graph: &'a GraphProjection,
    first: Buffer<usize>,
    second: Buffer<usize>,
}

impl<'a> Pairs<'a> {
    fn new(graph: &'a GraphProjection, count: usize) -> Result<Self> {
        let context = graph.execution();
        Ok(Self {
            graph,
            first: Buffer::capacity(count, context)?,
            second: Buffer::capacity(count, context)?,
        })
    }
    fn push(&mut self, a: &str, b: &str) -> Result<()> {
        let row = |id: &str| {
            self.graph
                .source(id)
                .map_err(|_| invalid(format!("candidate node {id} is not in the projection")))
        };
        let (a, b) = (row(a)?, row(b)?);
        self.first.values.push(a);
        self.second.values.push(b);
        Ok(())
    }
    fn finish(self) -> CandidatePairs {
        CandidatePairs {
            graph: self.graph.clone(),
            first: self.first,
            second: self.second,
        }
    }
}

/// Link prediction controls.
#[derive(Clone, Copy, Default)]
pub struct LinkPredictionOptions<'a> {
    /// The score.
    pub metric: LinkMetric,
    /// The pairs scored.
    pub candidates: LinkCandidates<'a>,
    /// For [`LinkMetric::SameCommunity`] only, and required by it: properties
    /// read against this projection, and the key of an integer column holding
    /// each node's community id. Any other metric refuses it rather than
    /// silently not reading it.
    pub communities: Option<(&'a NodeProperties, &'a str)>,
}

/// One score per candidate pair.
pub struct LinkPrediction {
    graph: GraphProjection,
    first: Buffer<usize>,
    second: Buffer<usize>,
    score: Buffer<f64>,
}

impl LinkPrediction {
    /// Projection supplying external ids and snapshot identity.
    pub fn projection(&self) -> &GraphProjection {
        &self.graph
    }
    /// `node1` per row, as a projection row.
    pub fn first(&self) -> &[usize] {
        &self.first.values
    }
    /// `node2` per row, as a projection row.
    pub fn second(&self) -> &[usize] {
        &self.second.values
    }
    /// Score per row.
    pub fn scores(&self) -> &[f64] {
        &self.score.values
    }
    /// Rows of `node1`, `node2`, `score`.
    pub fn into_table(self) -> Result<NodeTable> {
        NodeTable::keyed(&self.graph, "node1", self.first)?
            .column("node2", NodeColumn::Node(self.second))?
            .column("score", NodeColumn::Number(self.score))
    }
}

/// Score candidate node pairs by one of NetworKit's six link predictors.
///
/// **Undirected only**, as in NetworKit: a directed projection is refused.
/// Weights are not read; every metric is topological.
///
/// **Sets, as in `nodeSimilarity`.** `N(x)` is the set of distinct neighbours
/// of `x`, so parallel edges collapse and a self-loop is not a neighbour, and
/// every degree above is `|N(x)|`. On a simple graph this is NetworKit's
/// `degree`; on a multigraph NetworKit would count each parallel edge.
///
/// **Edge cases, decided.** A pair `(u, u)` scores `0` under every metric,
/// as in NetworKit's `LinkPredictor::run`; without that rule Adamic–Adar would
/// divide by `ln 1 = 0` for a neighbour whose only neighbour is `u`. For
/// `u ≠ v` a common neighbour `w` has both in `N(w)`, so `|N(w)| ≥ 2` and
/// `ln |N(w)| ≥ ln 2`: Adamic–Adar is always finite, and a pair sharing no
/// neighbour scores `0` for the three intersection metrics. An isolated node
/// scores `0` against anything except under total neighbours, where it
/// contributes nothing to the union, and same community, which does not look
/// at edges. Sums over shared neighbours run in ascending row order.
///
/// **Same community** reads ids from a node property the caller supplies (for
/// instance a Louvain result); NetworKit computes its own partition with PLM.
///
/// **Cost.** Building the sets is `O(m log d)`; a pair costs
/// `|N(u)| + |N(v)|` for the neighbour metrics and `O(1)` for the other two;
/// distance-two enumeration walks every `(u, w, v)` path once per `u`.
/// Everything is charged; sequential.
pub fn link_prediction(
    graph: &GraphProjection,
    options: LinkPredictionOptions<'_>,
) -> Result<LinkPrediction> {
    graph.require_nonnegative("linkPrediction")?;
    let context = graph.execution();
    context.checkpoint()?;
    if graph.orientation() != Orientation::Undirected {
        return Err(invalid(
            "linkPrediction is defined on undirected graphs; project with orientation undirected"
                .into(),
        ));
    }
    let same = |other: &GraphProjection| std::ptr::eq(graph.node_ids(), other.node_ids());
    let communities = match (options.metric, options.communities) {
        (LinkMetric::SameCommunity, Some((properties, key))) => {
            if !same(properties.projection()) {
                return Err(invalid(
                    "community properties were read against another projection".into(),
                ));
            }
            Some(properties.integers(key)?)
        }
        (LinkMetric::SameCommunity, None) => {
            return Err(invalid(
                "metric sameCommunity needs a community property".into(),
            ));
        }
        (_, Some(_)) => {
            return Err(invalid(
                "only metric sameCommunity reads a community property".into(),
            ));
        }
        (_, None) => None,
    };
    if let LinkCandidates::Pairs(pairs) = options.candidates
        && !same(&pairs.graph)
    {
        return Err(invalid(
            "candidate pairs were resolved against another projection".into(),
        ));
    }

    let sets = Sets::build(graph, context)?;
    let scorer = Scorer {
        sets: &sets,
        metric: options.metric,
        communities,
    };
    let mut meter = context.work_meter();
    let mut out = Rows::new(
        match options.candidates {
            LinkCandidates::Pairs(pairs) => pairs.len(),
            LinkCandidates::DistanceTwo => graph.node_count().min(1024),
        },
        context,
    )?;
    match options.candidates {
        LinkCandidates::Pairs(pairs) => {
            for (&u, &v) in pairs.first().iter().zip(pairs.second()) {
                let score = scorer.score(u, v, &mut meter)?;
                out.push(u, v, score, context)?;
            }
        }
        LinkCandidates::DistanceTwo => {
            let n = graph.node_count();
            // `near[x] == u + 1`: x is u's neighbour; `found[x] == u + 1`: x is
            // already u's candidate. Stamps, so nothing is cleared per node.
            let mut near = Buffer::filled(n, 0usize, context)?;
            let mut found = Buffer::filled(n, 0usize, context)?;
            let mut list: Buffer<usize> = Buffer::capacity(n, context)?;
            for u in 0..n {
                let stamp = u + 1;
                let own = sets.of(u);
                meter.charge(1 + own.len())?;
                for &w in own {
                    near.values[w] = stamp;
                }
                for &w in own {
                    let theirs = sets.of(w);
                    meter.charge(1 + theirs.len())?;
                    for &v in theirs {
                        if v > u && near.values[v] != stamp && found.values[v] != stamp {
                            found.values[v] = stamp;
                            list.values.push(v);
                        }
                    }
                }
                let count = list.values.len();
                meter.charge(count.saturating_mul(count.max(2).ilog2() as usize))?;
                list.values.sort_unstable();
                for &v in &list.values {
                    let score = scorer.score(u, v, &mut meter)?;
                    out.push(u, v, score, context)?;
                }
                list.values.clear();
            }
        }
    }
    Ok(LinkPrediction {
        graph: graph.clone(),
        first: out.first,
        second: out.second,
        score: out.score,
    })
}

fn invalid(message: String) -> AlgorithmError {
    AlgorithmError::InvalidArguments(message)
}

/// Distinct neighbours per node, self excluded, ascending.
struct Sets {
    offsets: Buffer<usize>,
    neighbours: Buffer<usize>,
}

impl Sets {
    fn build(graph: &GraphProjection, context: &ExecutionContext) -> Result<Self> {
        let adjacency = graph.outgoing();
        let n = graph.node_count();
        let mut meter = context.work_meter();
        let mut offsets = Buffer::capacity(n + 1, context)?;
        let mut neighbours = Buffer::capacity(adjacency.arc_count(), context)?;
        offsets.values.push(0);
        for node in 0..n {
            let range = adjacency.range(node);
            let degree = range.len();
            meter.charge(1 + degree.saturating_mul(degree.max(2).ilog2() as usize))?;
            let start = neighbours.values.len();
            neighbours
                .values
                .extend(adjacency.row_targets(node).filter(|&target| target != node));
            neighbours.values[start..].sort_unstable();
            let mut write = start;
            for read in start..neighbours.values.len() {
                let target = neighbours.values[read];
                if write == start || neighbours.values[write - 1] != target {
                    neighbours.values[write] = target;
                    write += 1;
                }
            }
            neighbours.values.truncate(write);
            offsets.values.push(write);
        }
        Ok(Self {
            offsets,
            neighbours,
        })
    }

    fn of(&self, node: usize) -> &[usize] {
        &self.neighbours.values[self.offsets.values[node]..self.offsets.values[node + 1]]
    }
}

struct Scorer<'a> {
    sets: &'a Sets,
    metric: LinkMetric,
    communities: Option<&'a [i64]>,
}

impl Scorer<'_> {
    fn score(&self, u: usize, v: usize, meter: &mut WorkMeter) -> Result<f64> {
        meter.charge(1)?;
        if u == v {
            return Ok(0.0);
        }
        let (a, b) = (self.sets.of(u), self.sets.of(v));
        match self.metric {
            LinkMetric::PreferentialAttachment => return Ok(a.len() as f64 * b.len() as f64),
            LinkMetric::SameCommunity => {
                let communities = self.communities.expect("validated: sameCommunity has ids");
                return Ok(if communities[u] == communities[v] {
                    1.0
                } else {
                    0.0
                });
            }
            _ => {}
        }
        meter.charge(a.len() + b.len())?;
        let (mut i, mut j) = (0, 0);
        let (mut common, mut sum) = (0usize, 0.0f64);
        while i < a.len() && j < b.len() {
            match a[i].cmp(&b[j]) {
                std::cmp::Ordering::Less => i += 1,
                std::cmp::Ordering::Greater => j += 1,
                std::cmp::Ordering::Equal => {
                    let degree = self.sets.of(a[i]).len();
                    // u and v are both in N(w), and are distinct.
                    debug_assert!(degree >= 2);
                    common += 1;
                    sum += match self.metric {
                        LinkMetric::AdamicAdar => 1.0 / (degree as f64).ln(),
                        LinkMetric::ResourceAllocation => 1.0 / degree as f64,
                        _ => 0.0,
                    };
                    i += 1;
                    j += 1;
                }
            }
        }
        Ok(match self.metric {
            LinkMetric::CommonNeighbors => common as f64,
            LinkMetric::TotalNeighbors => (a.len() + b.len() - common) as f64,
            _ => sum,
        })
    }
}

/// Output rows, grown by doubling with each larger buffer admitted first.
struct Rows {
    first: Buffer<usize>,
    second: Buffer<usize>,
    score: Buffer<f64>,
    /// Rows admitted; pushing past it would allocate unadmitted memory.
    limit: usize,
}

impl Rows {
    fn new(capacity: usize, context: &ExecutionContext) -> Result<Self> {
        Ok(Self {
            first: Buffer::capacity(capacity, context)?,
            second: Buffer::capacity(capacity, context)?,
            score: Buffer::capacity(capacity, context)?,
            limit: capacity,
        })
    }

    fn push(&mut self, u: usize, v: usize, score: f64, context: &ExecutionContext) -> Result<()> {
        if self.first.values.len() == self.limit {
            let wanted = self.limit.saturating_mul(2).max(16);
            grow(&mut self.first, wanted, context)?;
            grow(&mut self.second, wanted, context)?;
            grow(&mut self.score, wanted, context)?;
            self.limit = wanted;
        }
        self.first.values.push(u);
        self.second.values.push(v);
        self.score.values.push(score);
        Ok(())
    }
}

fn grow<T: Copy>(
    buffer: &mut Buffer<T>,
    capacity: usize,
    context: &ExecutionContext,
) -> Result<()> {
    context.charge_work(buffer.values.len())?;
    let mut larger = Buffer::capacity(capacity, context)?;
    larger.values.extend_from_slice(&buffer.values);
    *buffer = larger;
    Ok(())
}

//! Node similarity: nodes are alike when they point at the same things.

use crate::{
    AlgorithmError, GraphProjection, Result,
    buffer::Buffer,
    meter::Meter,
    parallel,
    table::{NodeColumn, NodeTable},
};
use grust_procedures::ExecutionContext;

/// How two neighbour sets are compared. `S` sums, over shared neighbours, the
/// smaller of the two weights (Jaccard, overlap) or their product (cosine);
/// without weights every weight is one and `S` is the size of the intersection.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum SimilarityMetric {
    /// `S / (W(a) + W(b) - S)`: intersection over union.
    #[default]
    Jaccard,
    /// `S / min(W(a), W(b))`: one when one set contains the other.
    Overlap,
    /// `S / (|a| |b|)`, the cosine of the two weight vectors.
    Cosine,
}

/// Node similarity controls.
#[derive(Clone, Copy, Debug)]
pub struct NodeSimilarityOptions {
    /// The comparison.
    pub metric: SimilarityMetric,
    /// Keep, for each node, its this-many most similar nodes.
    pub top_k: usize,
    /// Then keep the this-many most similar rows overall; zero keeps all.
    pub top_n: usize,
    /// Drop pairs below this. Pairs with no shared neighbour are never emitted.
    pub similarity_cutoff: f64,
    /// Leave out nodes with fewer distinct neighbours than this.
    pub degree_cutoff: usize,
    /// Leave out nodes with more distinct neighbours than this.
    pub upper_degree_cutoff: Option<usize>,
}

impl Default for NodeSimilarityOptions {
    fn default() -> Self {
        Self {
            metric: SimilarityMetric::Jaccard,
            top_k: 10,
            top_n: 0,
            similarity_cutoff: 0.0,
            degree_cutoff: 1,
            upper_degree_cutoff: None,
        }
    }
}

/// Similar pairs, one row per kept `(node1, node2)`.
pub struct NodeSimilarity {
    graph: GraphProjection,
    first: Buffer<usize>,
    second: Buffer<usize>,
    similarity: Buffer<f64>,
}

impl NodeSimilarity {
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
    /// Similarity per row, in `(0, 1]`.
    pub fn similarity(&self) -> &[f64] {
        &self.similarity.values
    }
    /// Rows of `node1`, `node2`, `similarity`.
    pub fn into_table(self) -> Result<NodeTable> {
        NodeTable::keyed(&self.graph, "node1", self.first)?
            .column("node2", NodeColumn::Node(self.second))?
            .column("similarity", NodeColumn::Number(self.similarity))
    }
}

/// Compare every two nodes by what their arcs point at.
///
/// **Sets, not multisets.** A node's neighbours are the *distinct* nodes its
/// arcs reach, itself excluded. Parallel edges collapse into one neighbour:
/// without weights it simply is in the set, and with weights it carries their
/// sum. The degree-style kernels here count each parallel edge instead.
///
/// **Rows.** A pair sharing no neighbour, or scoring zero, is never emitted.
/// Each kept pair appears from both sides, `(a, b)` and `(b, a)`, because
/// `top_k` is per `node1`: `b` may be among `a`'s closest without the reverse.
/// Rows come ordered by `node1`, then by similarity descending, then `node2`;
/// with `top_n`, by similarity descending, then `node1`, then `node2`.
///
/// **Cost** is the number of `(a, shared neighbour, b)` triples, which a
/// popular neighbour makes quadratic in its popularity. Every triple is charged,
/// so the work budget is the guard; `upper_degree_cutoff` does not help there,
/// as it bounds a node's own neighbours, not how many point at it.
///
/// Rows and charged work are identical at any pool width.
pub fn node_similarity(
    graph: &GraphProjection,
    options: NodeSimilarityOptions,
) -> Result<NodeSimilarity> {
    let context = graph.execution();
    context.checkpoint()?;
    let invalid = |message: &str| Err(AlgorithmError::InvalidArguments(message.into()));
    if options.top_k == 0 {
        return invalid("topK must be positive");
    }
    if !(0.0..=1.0).contains(&options.similarity_cutoff) {
        return invalid("similarityCutoff must be between 0 and 1");
    }
    if options.degree_cutoff == 0 {
        return invalid("degreeCutoff must be positive");
    }
    if options
        .upper_degree_cutoff
        .is_some_and(|upper| upper < options.degree_cutoff)
    {
        return invalid("upperDegreeCutoff must not be below degreeCutoff");
    }

    let sets = Sets::build(graph, options, context)?;
    let n = sets.nodes();
    let blocks = n.div_ceil(BLOCK);
    let mut chunks: Buffer<Buffer<Row>> = Buffer::capacity(blocks, context)?;
    let mut total = 0usize;
    parallel::ordered_blocks(
        blocks,
        |block| {
            let first = block * BLOCK;
            let last = (first + BLOCK).min(n);
            let mut workspace = Workspace::new(n, options.top_k, context)?;
            for node in first..last {
                workspace.rank(&sets, node, options, context)?;
            }
            // Keep exactly what was found; the scratch goes back.
            let mut kept = Buffer::capacity(workspace.rows.values.len(), context)?;
            kept.values.extend_from_slice(&workspace.rows.values);
            Ok(kept)
        },
        |_, kept: Buffer<Row>| {
            total += kept.values.len();
            chunks.values.push(kept);
            Ok(())
        },
    )?;

    let mut meter = Meter::new(context);
    let mut rows = Buffer::capacity(total, context)?;
    for chunk in chunks.values.drain(..) {
        meter.tick(chunk.values.len())?;
        rows.values.extend_from_slice(&chunk.values);
    }
    drop(chunks);
    if options.top_n > 0 {
        meter.tick(total.saturating_mul(total.max(2).ilog2() as usize))?;
        rows.values.sort_unstable_by(|a, b| {
            b.similarity
                .total_cmp(&a.similarity)
                .then(a.first.cmp(&b.first))
                .then(a.second.cmp(&b.second))
        });
        rows.values.truncate(options.top_n);
    }
    let count = rows.values.len();
    meter.tick(count)?;
    let mut first = Buffer::capacity(count, context)?;
    let mut second = Buffer::capacity(count, context)?;
    let mut similarity = Buffer::capacity(count, context)?;
    for row in &rows.values {
        first.values.push(row.first);
        second.values.push(row.second);
        similarity.values.push(row.similarity);
    }
    meter.flush()?;
    Ok(NodeSimilarity {
        graph: graph.clone(),
        first,
        second,
        similarity,
    })
}

/// Nodes per block; fixed, so nothing depends on the pool width.
const BLOCK: usize = 64;

#[derive(Clone, Copy)]
struct Row {
    first: usize,
    second: usize,
    similarity: f64,
}

/// Distinct neighbours per node, and per neighbour the nodes that have it.
struct Sets {
    offsets: Buffer<usize>,
    /// (neighbour, weight), ascending by neighbour within a row.
    entries: Buffer<(usize, f64)>,
    member_offsets: Buffer<usize>,
    /// (node, weight), ascending by node within a row.
    members: Buffer<(usize, f64)>,
    /// `W`: the weights' sum, or for cosine their Euclidean norm.
    measure: Buffer<f64>,
    /// Whether the degree cutoffs admit the node.
    admitted: Buffer<bool>,
}

impl Sets {
    fn nodes(&self) -> usize {
        self.measure.values.len()
    }

    fn build(
        graph: &GraphProjection,
        options: NodeSimilarityOptions,
        context: &ExecutionContext,
    ) -> Result<Self> {
        let adjacency = graph.outgoing();
        let weighted = adjacency.weights.is_some();
        let n = graph.node_count();
        let mut meter = Meter::new(context);
        let mut offsets = Buffer::capacity(n + 1, context)?;
        let mut entries: Buffer<(usize, f64)> =
            Buffer::capacity(adjacency.targets.values.len(), context)?;
        let mut measure = Buffer::capacity(n, context)?;
        let mut admitted = Buffer::capacity(n, context)?;
        let mut member_offsets = Buffer::filled(n + 1, 0usize, context)?;
        offsets.values.push(0);
        for node in 0..n {
            let range = adjacency.range(node);
            let degree = range.len();
            meter.tick(1 + degree.saturating_mul(degree.max(2).ilog2() as usize))?;
            let start = entries.values.len();
            for arc in range {
                let target = adjacency.targets.values[arc];
                if target != node {
                    entries.values.push((target, adjacency.weight(arc)));
                }
            }
            // Ordering equal neighbours by weight fixes the order their sum is taken in.
            entries.values[start..]
                .sort_unstable_by(|a, b| a.0.cmp(&b.0).then(a.1.total_cmp(&b.1)));
            let mut write = start;
            for read in start..entries.values.len() {
                let entry = entries.values[read];
                if write > start && entries.values[write - 1].0 == entry.0 {
                    // Without weights a neighbour is in the set or not.
                    if weighted {
                        entries.values[write - 1].1 += entry.1;
                    }
                } else {
                    entries.values[write] = entry;
                    write += 1;
                }
            }
            entries.values.truncate(write);
            let distinct = write - start;
            admitted.values.push(
                distinct >= options.degree_cutoff
                    && options
                        .upper_degree_cutoff
                        .is_none_or(|upper| distinct <= upper),
            );
            let row = &entries.values[start..];
            measure.values.push(match options.metric {
                SimilarityMetric::Cosine => row.iter().map(|e| e.1 * e.1).sum::<f64>().sqrt(),
                _ => row.iter().map(|e| e.1).sum(),
            });
            if admitted.values[node] {
                for &(target, _) in row {
                    member_offsets.values[target + 1] += 1;
                }
            }
            offsets.values.push(write);
        }
        // Only admitted nodes are anyone's candidate, so only they are members.
        for index in 1..=n {
            member_offsets.values[index] += member_offsets.values[index - 1];
        }
        meter.tick(n + entries.values.len())?;
        let mut members = Buffer::filled(member_offsets.values[n], (0usize, 0.0f64), context)?;
        let mut position = Buffer::capacity(n, context)?;
        position
            .values
            .extend_from_slice(&member_offsets.values[..n]);
        for node in 0..n {
            if !admitted.values[node] {
                continue;
            }
            for &(target, weight) in &entries.values[offsets.values[node]..offsets.values[node + 1]]
            {
                members.values[position.values[target]] = (node, weight);
                position.values[target] += 1;
            }
        }
        meter.flush()?;
        Ok(Self {
            offsets,
            entries,
            member_offsets,
            members,
            measure,
            admitted,
        })
    }
}

struct Workspace {
    /// `S` per candidate for the node in hand.
    shared: Buffer<f64>,
    seen: Buffer<bool>,
    candidates: Buffer<usize>,
    ranked: Buffer<Row>,
    rows: Buffer<Row>,
}

impl Workspace {
    fn new(n: usize, top_k: usize, context: &ExecutionContext) -> Result<Self> {
        Ok(Self {
            shared: Buffer::filled(n, 0.0, context)?,
            seen: Buffer::filled(n, false, context)?,
            candidates: Buffer::capacity(n, context)?,
            ranked: Buffer::capacity(n, context)?,
            // Enough for every node of a block to keep `top_k` partners, up to
            // 1024 each; `rank` admits more before it is needed.
            rows: Buffer::capacity(BLOCK * top_k.min(n.saturating_sub(1)).min(1024), context)?,
        })
    }

    fn rank(
        &mut self,
        sets: &Sets,
        node: usize,
        options: NodeSimilarityOptions,
        context: &ExecutionContext,
    ) -> Result<()> {
        if !sets.admitted.values[node] {
            return Ok(());
        }
        let mut meter = Meter::new(context);
        let cosine = options.metric == SimilarityMetric::Cosine;
        for &(target, weight) in
            &sets.entries.values[sets.offsets.values[node]..sets.offsets.values[node + 1]]
        {
            let members = &sets.members.values
                [sets.member_offsets.values[target]..sets.member_offsets.values[target + 1]];
            meter.tick(1 + members.len())?;
            for &(other, other_weight) in members {
                if other == node {
                    continue;
                }
                if !self.seen.values[other] {
                    self.seen.values[other] = true;
                    self.candidates.values.push(other);
                }
                self.shared.values[other] += if cosine {
                    weight * other_weight
                } else {
                    weight.min(other_weight)
                };
            }
        }
        let own = sets.measure.values[node];
        for &other in &self.candidates.values {
            let shared = self.shared.values[other];
            let theirs = sets.measure.values[other];
            self.shared.values[other] = 0.0;
            self.seen.values[other] = false;
            let denominator = match options.metric {
                SimilarityMetric::Jaccard => own + theirs - shared,
                SimilarityMetric::Overlap => own.min(theirs),
                SimilarityMetric::Cosine => own * theirs,
            };
            let similarity = shared / denominator;
            // Zero weights can leave nothing shared, or nothing to divide by.
            if similarity > 0.0 && similarity.is_finite() && similarity >= options.similarity_cutoff
            {
                self.ranked.values.push(Row {
                    first: node,
                    second: other,
                    similarity,
                });
            }
        }
        let found = self.ranked.values.len();
        meter.tick(
            self.candidates.values.len() + found.saturating_mul(found.max(2).ilog2() as usize),
        )?;
        self.candidates.values.clear();
        let order = |a: &Row, b: &Row| {
            b.similarity
                .total_cmp(&a.similarity)
                .then(a.second.cmp(&b.second))
        };
        if found > options.top_k {
            self.ranked
                .values
                .select_nth_unstable_by(options.top_k, order);
            self.ranked.values.truncate(options.top_k);
        }
        self.ranked.values.sort_unstable_by(order);
        if self.rows.values.len() + self.ranked.values.len() > self.rows.values.capacity() {
            // Only when `top_k` exceeds 1024: admit the larger scratch first.
            let mut larger = Buffer::capacity(
                (self.rows.values.len() + self.ranked.values.len()).saturating_mul(2),
                context,
            )?;
            larger.values.extend_from_slice(&self.rows.values);
            self.rows = larger;
        }
        self.rows.values.extend_from_slice(&self.ranked.values);
        self.ranked.values.clear();
        meter.flush()
    }
}

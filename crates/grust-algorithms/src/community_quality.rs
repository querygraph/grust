//! Modularity and conductance of a given community assignment.

use std::collections::HashMap;

use crate::{
    AlgorithmError, NodeProperties, Orientation, Result,
    buffer::Buffer,
    table::{NodeColumn, NodeTable, TableScalar},
};

/// How good a partition is, community by community.
pub struct CommunityQuality {
    properties_graph: crate::GraphProjection,
    representative: Buffer<usize>,
    community: Buffer<i64>,
    size: Buffer<i64>,
    modularity: Buffer<f64>,
    conductance: Buffer<f64>,
    total: f64,
}

impl CommunityQuality {
    /// Projection supplying external ids and snapshot identity.
    pub fn projection(&self) -> &crate::GraphProjection {
        &self.properties_graph
    }
    /// Communities, in order of their smallest member row.
    pub fn communities(&self) -> &[i64] {
        &self.community.values
    }
    /// Smallest member row per community.
    pub fn representatives(&self) -> &[usize] {
        &self.representative.values
    }
    /// Members per community.
    pub fn sizes(&self) -> &[i64] {
        &self.size.values
    }
    /// Each community's share of the modularity; they sum to [`Self::modularity`].
    pub fn modularity_parts(&self) -> &[f64] {
        &self.modularity.values
    }
    /// Conductance per community; NaN where the community has no weight at all.
    pub fn conductances(&self) -> &[f64] {
        &self.conductance.values
    }
    /// Modularity of the whole assignment.
    pub fn modularity(&self) -> f64 {
        self.total
    }

    /// One row per community, led by its smallest member as `nodeId`:
    /// `communityId`, `size`, `modularity`, `conductance` (null where undefined),
    /// then the `totalModularity` scalar.
    pub fn into_table(self) -> Result<NodeTable> {
        Ok(
            NodeTable::keyed(&self.properties_graph, "nodeId", self.representative)?
                .column("communityId", NodeColumn::Integer(self.community))?
                .column("size", NodeColumn::Integer(self.size))?
                .column("modularity", NodeColumn::Number(self.modularity))?
                .column("conductance", NodeColumn::OptionalNumber(self.conductance))?
                .scalar("totalModularity", TableScalar::Number(self.total)),
        )
    }
}

/// Score the communities named by the integer property `key`.
///
/// **Modularity** is the one Louvain and Leiden optimise, by the same formula
/// for every orientation: a community contributes `in/M - γ·out·into/M²`, where
/// `in` is the weight of arcs inside it, `out` and `into` the weight leaving and
/// entering its nodes, and `M` the total. On an undirected projection that is
/// Newman's modularity; otherwise Leicht and Newman's. An undirected self-loop
/// counts twice, as it does in the adjacency matrix. A graph with no weight
/// scores zero.
///
/// **Conductance** of a community is the share of the weight leaving its nodes
/// that also leaves the community: `cut / volume`, zero for a community nothing
/// leaves, and undefined (null) for one whose nodes have no arcs. Low is good.
/// On a directed projection it follows arcs out of the community.
///
/// Community ids are any integers; nothing assumes they are dense, small or
/// nonnegative. Parallel edges add their weights. Sequential: one pass over the
/// arcs.
pub fn community_quality(
    properties: &NodeProperties,
    key: &str,
    resolution: f64,
) -> Result<CommunityQuality> {
    let graph = properties.projection();
    graph.require_nonnegative("modularity and conductance")?;
    let context = graph.execution();
    context.checkpoint()?;
    if !resolution.is_finite() || resolution < 0.0 {
        return Err(AlgorithmError::InvalidArguments(
            "resolution must be finite and nonnegative".into(),
        ));
    }
    let labels = properties.integers(key)?;
    let n = graph.node_count();
    let adjacency = graph.outgoing();
    let undirected = graph.orientation() == Orientation::Undirected;
    let mut meter = context.work_meter();

    // Dense index per community, in order of first appearance, which is order
    // of smallest member row.
    let mut account = context.memory_account();
    let mut index_of: HashMap<i64, usize> = HashMap::new();
    let mut dense = Buffer::capacity(n, context)?;
    let mut representative = Buffer::capacity(n, context)?;
    let mut community = Buffer::capacity(n, context)?;
    for (row, &label) in labels.iter().enumerate() {
        meter.charge(1)?;
        let next = index_of.len();
        let index = match index_of.get(&label) {
            Some(&index) => index,
            None => {
                account.charge(3 * size_of::<(i64, usize)>())?;
                index_of.try_reserve(1)?;
                index_of.insert(label, next);
                representative.values.push(row);
                community.values.push(label);
                next
            }
        };
        dense.values.push(index);
    }
    let count = community.values.len();
    drop(index_of);
    drop(account);

    let mut size = Buffer::filled(count, 0i64, context)?;
    let mut inside = Buffer::filled(count, 0.0f64, context)?;
    let mut out = Buffer::filled(count, 0.0f64, context)?;
    let mut into = Buffer::filled(count, 0.0f64, context)?;
    let mut cut = Buffer::filled(count, 0.0f64, context)?;
    let mut total = 0.0f64;
    for source in 0..n {
        let here = dense.values[source];
        size.values[here] += 1;
        let range = adjacency.range(source);
        meter.charge(1 + range.len())?;
        for arc in range {
            let target = adjacency.target(arc);
            let there = dense.values[target];
            // An undirected loop occupies one arc and two matrix entries.
            let weight = if undirected && target == source {
                2.0 * adjacency.weight(arc)
            } else {
                adjacency.weight(arc)
            };
            total += weight;
            out.values[here] += weight;
            into.values[there] += weight;
            if here == there {
                inside.values[here] += weight;
            } else {
                cut.values[here] += weight;
            }
        }
    }
    if !total.is_finite() {
        return Err(AlgorithmError::Numerical(
            "total edge weight is not finite".into(),
        ));
    }

    let mut modularity = Buffer::capacity(count, context)?;
    let mut conductance = Buffer::capacity(count, context)?;
    let mut sum = 0.0;
    meter.charge(count)?;
    for index in 0..count {
        let part = if total > 0.0 {
            inside.values[index] / total
                - resolution * (out.values[index] / total) * (into.values[index] / total)
        } else {
            0.0
        };
        sum += part;
        modularity.values.push(part);
        conductance.values.push(if out.values[index] > 0.0 {
            cut.values[index] / out.values[index]
        } else {
            f64::NAN
        });
    }
    Ok(CommunityQuality {
        properties_graph: graph.clone(),
        representative,
        community,
        size,
        modularity,
        conductance,
        total: sum,
    })
}

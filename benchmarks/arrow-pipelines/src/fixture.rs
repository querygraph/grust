use grust_core::{Edge, Graph, Node, Props, Value};

#[derive(Clone, Copy, Debug)]
pub enum Workload {
    Scan,
    OneHop,
    TwoHop,
}
impl Workload {
    pub const ALL: [Self; 3] = [Self::Scan, Self::OneHop, Self::TwoHop];
    pub fn name(self) -> &'static str {
        match self {
            Self::Scan => "filtered_node_aggregate",
            Self::OneHop => "filtered_one_hop_aggregate",
            Self::TwoHop => "filtered_two_hop_trail_aggregate",
        }
    }
    pub fn cypher(self) -> &'static str {
        match self {
            Self::Scan => "MATCH (n:N) WHERE n.bucket = 3 RETURN count(*) AS c, sum(n.score) AS w",
            Self::OneHop => {
                "MATCH (a:N)-[e:E]->(b:N) WHERE a.bucket = 3 RETURN count(*) AS c, sum(e.weight) AS w"
            }
            Self::TwoHop => {
                "MATCH (a:N)-[e:E]->(b:N)-[f:E]->(c:N) WHERE a.bucket = 3 RETURN count(*) AS c, sum(f.weight) AS w"
            }
        }
    }
    pub fn sql(self) -> &'static str {
        match self {
            Self::Scan => {
                "SELECT COUNT(*) AS c, COALESCE(SUM(n.\"property.score\"), 0) AS w FROM g.graph.nodes n WHERE n.label = 'N' AND n.\"property.bucket\" = 3"
            }
            Self::OneHop => {
                "SELECT COUNT(*) AS c, COALESCE(SUM(e.\"property.weight\"), 0) AS w FROM g.graph.nodes a JOIN g.graph.edges e ON a.node_id = e.source JOIN g.graph.nodes b ON e.target = b.node_id WHERE a.label = 'N' AND b.label = 'N' AND e.label = 'E' AND a.\"property.bucket\" = 3"
            }
            Self::TwoHop => {
                "SELECT COUNT(*) AS c, COALESCE(SUM(f.\"property.weight\"), 0) AS w FROM g.graph.nodes a JOIN g.graph.edges e ON a.node_id = e.source JOIN g.graph.nodes b ON e.target = b.node_id JOIN g.graph.edges f ON b.node_id = f.source JOIN g.graph.nodes c ON f.target = c.node_id WHERE a.label = 'N' AND b.label = 'N' AND c.label = 'N' AND e.label = 'E' AND f.label = 'E' AND e.edge_id <> f.edge_id AND a.\"property.bucket\" = 3"
            }
        }
    }
}

pub fn graph(nodes: usize, degree: usize) -> Graph {
    let active = nodes - nodes / 10;
    let vertices = (0..nodes)
        .map(|i| {
            Node::new(
                "N",
                i.to_string(),
                Props::from([
                    ("bucket".into(), Value::Int((i % 16) as i64)),
                    ("score".into(), Value::Int((i % 101) as i64)),
                ]),
            )
        })
        .collect();
    let edges = (0..active)
        .flat_map(|from| {
            (0..degree).map(move |step| {
                Edge::new(
                    "E",
                    from.to_string(),
                    ((from + step) % active).to_string(),
                    Props::from([("weight".into(), Value::Int((step + 1) as i64))]),
                )
                .with_id((from * degree + step).to_string())
            })
        })
        .collect();
    Graph::new(vertices, edges)
}

/// Enumerate integer fixture coordinates independently of either query engine.
/// A trail may revisit a vertex, but cannot reuse the same edge identity.
pub fn expected(workload: Workload, nodes: usize, degree: usize) -> (i64, i64) {
    let active = nodes - nodes / 10;
    let mut count = 0i64;
    let mut sum = 0i64;
    match workload {
        Workload::Scan => {
            for node in (0..nodes).filter(|n| n % 16 == 3) {
                count += 1;
                sum += (node % 101) as i64;
            }
        }
        Workload::OneHop | Workload::TwoHop => {
            for source in (0..active).filter(|n| n % 16 == 3) {
                for first in 0..degree {
                    if matches!(workload, Workload::OneHop) {
                        count += 1;
                        sum += (first + 1) as i64;
                    } else {
                        let middle = (source + first) % active;
                        for second in 0..degree {
                            if (source, first) != (middle, second) {
                                count += 1;
                                sum += (second + 1) as i64;
                            }
                        }
                    }
                }
            }
        }
    }
    (count, sum)
}

#[cfg(test)]
#[path = "fixture_tests.rs"]
mod tests;

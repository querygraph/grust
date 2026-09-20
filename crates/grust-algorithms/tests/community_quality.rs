//! Modularity and conductance against their definitions over a dense matrix.

use grust_algorithms::{
    ExecutionContext, ExecutionLimits, GraphProjection, LouvainOptions, MissingWeight,
    NodeProperties, Orientation, ProjectionOptions, PropertyKind, PropertyRequest,
    SnapshotIdentity, WeightSelection, community_quality, louvain,
};
use grust_core::{Edge, Graph, Node, Props, Value};

const ORIENTATIONS: [Orientation; 3] = [
    Orientation::Undirected,
    Orientation::Outgoing,
    Orientation::Incoming,
];

fn context() -> ExecutionContext {
    ExecutionContext::new(ExecutionLimits {
        memory_bytes: 64 * 1024 * 1024,
        work_units: 100_000_000,
        batch_rows: 1024,
        deadline: None,
    })
    .unwrap()
}

fn build(n: usize, edges: &[(usize, usize, f64)], communities: &[i64]) -> Graph {
    Graph::new(
        (0..n)
            .map(|i| {
                Node::new(
                    "N",
                    format!("n{i}"),
                    Props::from([("c".to_string(), Value::Int(communities[i]))]),
                )
            })
            .collect(),
        edges
            .iter()
            .map(|&(a, b, w)| {
                Edge::new(
                    "R",
                    format!("n{a}"),
                    format!("n{b}"),
                    [("w".to_string(), Value::Float(w))],
                )
            })
            .collect(),
    )
}

fn project(graph: &Graph, orientation: Orientation, context: &ExecutionContext) -> GraphProjection {
    GraphProjection::from_graph(
        graph,
        SnapshotIdentity::new("g".into(), "r".into(), "reader".into()).unwrap(),
        ProjectionOptions {
            orientation,
            weight: WeightSelection::Property {
                key: "w",
                missing: MissingWeight::Reject,
            },
            ..Default::default()
        },
        context,
    )
    .unwrap()
}

/// `a[i][j]`: weight of arcs i -> j as traversed; an undirected loop is 2w.
fn matrix(n: usize, edges: &[(usize, usize, f64)], orientation: Orientation) -> Vec<Vec<f64>> {
    let mut a = vec![vec![0.0; n]; n];
    for &(s, t, w) in edges {
        match orientation {
            Orientation::Undirected => {
                a[s][t] += w;
                a[t][s] += w;
            }
            Orientation::Outgoing => a[s][t] += w,
            Orientation::Incoming => a[t][s] += w,
        }
    }
    a
}

/// Q = (1/M) Σ_ij [A_ij − γ k_out_i k_in_j / M] δ(c_i, c_j), from the papers.
fn modularity(a: &[Vec<f64>], communities: &[i64], gamma: f64) -> f64 {
    let n = a.len();
    let total: f64 = a.iter().flatten().sum();
    if total == 0.0 {
        return 0.0;
    }
    let k_out: Vec<f64> = a.iter().map(|row| row.iter().sum()).collect();
    let k_in: Vec<f64> = (0..n).map(|j| a.iter().map(|row| row[j]).sum()).collect();
    let mut q = 0.0;
    for i in 0..n {
        for j in 0..n {
            if communities[i] == communities[j] {
                q += a[i][j] - gamma * k_out[i] * k_in[j] / total;
            }
        }
    }
    q / total
}

/// Weight leaving the community over weight leaving its nodes.
fn conductance(a: &[Vec<f64>], communities: &[i64], community: i64) -> Option<f64> {
    let (mut cut, mut volume) = (0.0, 0.0);
    for (i, row) in a.iter().enumerate() {
        if communities[i] != community {
            continue;
        }
        for (j, &weight) in row.iter().enumerate() {
            volume += weight;
            if communities[j] != community {
                cut += weight;
            }
        }
    }
    (volume > 0.0).then(|| cut / volume)
}

struct Xorshift(u64);
impl Xorshift {
    fn below(&mut self, bound: usize) -> usize {
        self.0 ^= self.0 << 13;
        self.0 ^= self.0 >> 7;
        self.0 ^= self.0 << 17;
        (self.0 % bound as u64) as usize
    }
}

#[test]
fn every_figure_matches_its_definition_on_random_multigraphs() {
    let mut random = Xorshift(0x2545_F491_4F6C_DD1D);
    for round in 0..600 {
        let n = 1 + random.below(10);
        let count = random.below(3 * n);
        let edges: Vec<_> = (0..count)
            .map(|_| (random.below(n), random.below(n), random.below(4) as f64))
            .collect();
        // Ids that are sparse, negative and unordered: nothing may assume dense.
        let ids = [-40i64, 7, 1_000_000_007, 0];
        let communities: Vec<i64> = (0..n).map(|_| ids[random.below(1 + round % 4)]).collect();
        let gamma = [1.0, 0.5, 2.0][round % 3];
        let graph = build(n, &edges, &communities);
        for orientation in ORIENTATIONS {
            let what = format!("{orientation:?} γ={gamma} {edges:?} {communities:?}");
            let context = context();
            let projection = project(&graph, orientation, &context);
            let properties = NodeProperties::from_graph(
                &graph,
                &projection,
                &[PropertyRequest::required("c", PropertyKind::Integer)],
            )
            .unwrap();
            let result = community_quality(&properties, "c", gamma).unwrap();
            let a = matrix(n, &edges, orientation);
            assert!(
                (result.modularity() - modularity(&a, &communities, gamma)).abs() < 1e-12,
                "{what}"
            );
            let parts: f64 = result.modularity_parts().iter().sum();
            assert!((parts - result.modularity()).abs() < 1e-12, "{what}");
            // Communities come in order of their smallest member, each once.
            let mut seen = Vec::new();
            for &c in &communities {
                if !seen.contains(&c) {
                    seen.push(c);
                }
            }
            assert_eq!(result.communities(), seen, "{what}");
            for (index, &c) in seen.iter().enumerate() {
                let members = communities.iter().filter(|&&x| x == c).count();
                assert_eq!(result.sizes()[index], members as i64, "{what}");
                assert_eq!(
                    communities[result.representatives()[index]],
                    c,
                    "{what}: representative is not a member"
                );
                match conductance(&a, &communities, c) {
                    Some(expected) => assert!(
                        (result.conductances()[index] - expected).abs() < 1e-12,
                        "{what}: community {c}"
                    ),
                    None => assert!(result.conductances()[index].is_nan(), "{what}"),
                }
            }
        }
    }
}

#[test]
fn two_triangles_joined_by_an_edge_score_what_the_textbook_says() {
    let edges = [
        (0, 1, 1.0),
        (1, 2, 1.0),
        (2, 0, 1.0),
        (3, 4, 1.0),
        (4, 5, 1.0),
        (5, 3, 1.0),
        (2, 3, 1.0),
    ];
    let communities = [10, 10, 10, 20, 20, 20];
    let graph = build(6, &edges, &communities);
    let context = context();
    let projection = project(&graph, Orientation::Undirected, &context);
    let properties = NodeProperties::from_graph(
        &graph,
        &projection,
        &[PropertyRequest::required("c", PropertyKind::Integer)],
    )
    .unwrap();
    let result = community_quality(&properties, "c", 1.0).unwrap();
    // Seven edges, so M = 14. Each triangle holds 6 of it and its nodes 7.
    let part = 6.0 / 14.0 - (7.0 / 14.0) * (7.0 / 14.0);
    assert_eq!(result.modularity_parts(), [part, part]);
    assert!((result.modularity() - 5.0 / 14.0).abs() < 1e-15);
    // One of a triangle's seven arc-ends leaves it.
    assert_eq!(result.conductances(), [1.0 / 7.0, 1.0 / 7.0]);
    assert_eq!(result.communities(), [10, 20]);
    assert_eq!(result.sizes(), [3, 3]);

    // It is the figure Louvain reports for the partition Louvain finds.
    let found = louvain(&projection, LouvainOptions::default()).unwrap();
    let as_property: Vec<i64> = found.communities().iter().map(|&c| c as i64).collect();
    let relabelled = build(6, &edges, &as_property);
    let projection = project(&relabelled, Orientation::Undirected, &context);
    let properties = NodeProperties::from_graph(
        &relabelled,
        &projection,
        &[PropertyRequest::required("c", PropertyKind::Integer)],
    )
    .unwrap();
    let scored = community_quality(&properties, "c", 1.0).unwrap();
    assert!((scored.modularity() - found.modularity()).abs() < 1e-12);

    // One community of everything has nothing to leave it, and scores zero.
    let whole = build(6, &edges, &[1; 6]);
    let projection = project(&whole, Orientation::Undirected, &context);
    let properties = NodeProperties::from_graph(
        &whole,
        &projection,
        &[PropertyRequest::required("c", PropertyKind::Integer)],
    )
    .unwrap();
    let result = community_quality(&properties, "c", 1.0).unwrap();
    assert!(result.modularity().abs() < 1e-15);
    assert_eq!(result.conductances(), [0.0]);
    assert!(community_quality(&properties, "c", f64::NAN).is_err());
    assert!(community_quality(&properties, "missing", 1.0).is_err());
}

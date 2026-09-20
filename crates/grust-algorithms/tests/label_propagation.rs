//! Label propagation: fixed points, planted cliques, schedule and limits.

use grust_algorithms::{
    AlgorithmError, ExecutionContext, ExecutionLimits, GraphProjection, LabelPropagationOptions,
    Orientation, ProjectionEdge, SnapshotIdentity, label_propagation,
};
use std::collections::BTreeMap;

const ORIENTATIONS: [Orientation; 3] = [
    Orientation::Outgoing,
    Orientation::Incoming,
    Orientation::Undirected,
];

fn limits(work_units: usize) -> ExecutionLimits {
    ExecutionLimits {
        memory_bytes: 64 * 1024 * 1024,
        work_units,
        batch_rows: 1024,
        deadline: None,
    }
}

fn context() -> ExecutionContext {
    ExecutionContext::new(limits(500_000_000)).unwrap()
}

fn graph(
    n: usize,
    edges: &[(usize, usize)],
    weights: Option<&[f64]>,
    orientation: Orientation,
    context: &ExecutionContext,
) -> GraphProjection {
    GraphProjection::from_topology(
        SnapshotIdentity::new("g".into(), "r".into(), "reader".into()).unwrap(),
        (0..n).map(|i| format!("n{i}").into()).collect(),
        edges
            .iter()
            .enumerate()
            .map(|(ordinal, &(source, target))| ProjectionEdge {
                source,
                target,
                ordinal,
                id: None,
            })
            .collect(),
        weights.map(<[f64]>::to_vec),
        orientation,
        context,
    )
    .unwrap()
}

/// Weight arriving at each node per community, straight from the edge list.
fn arriving(
    n: usize,
    edges: &[(usize, usize)],
    weights: Option<&[f64]>,
    orientation: Orientation,
    communities: &[usize],
) -> Vec<BTreeMap<usize, f64>> {
    let mut support = vec![BTreeMap::new(); n];
    for (index, &(a, b)) in edges.iter().enumerate() {
        let w = weights.map_or(1.0, |w| w[index]);
        let mut arc = |from: usize, to: usize| {
            *support[to].entry(communities[from]).or_insert(0.0) += w;
        };
        match orientation {
            Orientation::Outgoing => arc(a, b),
            Orientation::Incoming => arc(b, a),
            Orientation::Undirected => {
                arc(a, b);
                if a != b {
                    arc(b, a);
                }
            }
        }
    }
    support
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
fn a_converged_run_is_a_fixed_point_and_undirected_runs_always_converge() {
    let mut random = Xorshift(0x2545_F491_4F6C_DD1D);
    let mut converged_directed = 0;
    for round in 0..3000 {
        let n = 1 + random.below(12);
        let count = random.below(3 * n);
        let edges: Vec<_> = (0..count)
            .map(|_| (random.below(n), random.below(n)))
            .collect();
        let weights: Vec<f64> = (0..count).map(|_| random.below(4) as f64).collect();
        let weights = (round % 2 == 1).then_some(&weights[..]);
        let seed = (round % 3 == 0).then_some(round as u64);
        for orientation in ORIENTATIONS {
            let context = context();
            let result = label_propagation(
                &graph(n, &edges, weights, orientation, &context),
                LabelPropagationOptions {
                    max_iterations: 1000,
                    seed,
                },
            )
            .unwrap();
            let communities = result.communities();
            // Named by the smallest member, which is therefore a member.
            for (node, &community) in communities.iter().enumerate() {
                assert!(community <= node);
                assert_eq!(communities[community], community);
            }
            if orientation == Orientation::Undirected {
                assert!(result.converged(), "{edges:?} {weights:?}");
            }
            if !result.converged() {
                assert_eq!(result.iterations(), 1000);
                continue;
            }
            converged_directed += usize::from(orientation != Orientation::Undirected);
            // Nothing arriving at a node outweighs the community it holds.
            let support = arriving(n, &edges, weights, orientation, communities);
            for node in 0..n {
                let held = support[node]
                    .get(&communities[node])
                    .copied()
                    .unwrap_or(0.0);
                let heaviest = support[node].values().copied().fold(0.0, f64::max);
                assert!(
                    held >= heaviest,
                    "{orientation:?} {edges:?} {weights:?}: node {node} holds {held} of {heaviest}"
                );
            }
        }
    }
    assert!(
        converged_directed > 1000,
        "directed runs should mostly converge"
    );
}

#[test]
fn disjoint_cliques_separate_and_isolates_stay_alone() {
    let mut edges = Vec::new();
    for base in [0, 5, 10] {
        for a in base..base + 5 {
            for b in a + 1..base + 5 {
                edges.push((a, b));
            }
        }
    }
    for seed in [None, Some(1), Some(99)] {
        let context = context();
        let result = label_propagation(
            &graph(17, &edges, None, Orientation::Undirected, &context),
            LabelPropagationOptions {
                max_iterations: 10,
                seed,
            },
        )
        .unwrap();
        assert!(result.converged());
        let expected: Vec<usize> = (0..17)
            .map(|node| if node < 15 { node / 5 * 5 } else { node })
            .collect();
        assert_eq!(result.communities(), expected, "seed {seed:?}");
    }
    let context = context();
    let empty = label_propagation(
        &graph(0, &[], None, Orientation::Undirected, &context),
        LabelPropagationOptions::default(),
    )
    .unwrap();
    assert!(empty.communities().is_empty() && empty.converged());
    assert_eq!(empty.iterations(), 1);
}

#[test]
fn the_schedule_ties_and_direction_are_as_documented() {
    let context = context();
    // A directed 3-cycle in row order: 0 takes 2's label, 1 takes it from 0,
    // and the second pass changes nothing.
    let cycle = [(0, 1), (1, 2), (2, 0)];
    let run = |max_iterations| {
        label_propagation(
            &graph(3, &cycle, None, Orientation::Outgoing, &context),
            LabelPropagationOptions {
                max_iterations,
                seed: None,
            },
        )
        .unwrap()
    };
    let two = run(10);
    assert_eq!(two.communities(), [0, 0, 0]);
    assert_eq!((two.iterations(), two.converged()), (2, true));
    let one = run(1);
    assert_eq!((one.iterations(), one.converged()), (1, false));

    // Labels flow along arcs: a source with no in-arcs keeps its own label and
    // gives it to what it points at.
    let fan = label_propagation(
        &graph(3, &[(0, 1), (0, 2)], None, Orientation::Outgoing, &context),
        LabelPropagationOptions::default(),
    )
    .unwrap();
    assert_eq!(fan.communities(), [0, 0, 0]);
    let reversed = label_propagation(
        &graph(3, &[(0, 1), (0, 2)], None, Orientation::Incoming, &context),
        LabelPropagationOptions::default(),
    )
    .unwrap();
    // Node 0 hears 1 and 2 equally and takes the smaller; nothing reaches 1 or 2.
    assert_eq!(reversed.communities(), [0, 0, 2]);

    // Weight decides before the tie-break does, and a zero weight carries nothing.
    let weighted = label_propagation(
        &graph(
            4,
            &[(1, 0), (2, 0), (3, 0)],
            Some(&[1.0, 5.0, 0.0]),
            Orientation::Outgoing,
            &context,
        ),
        LabelPropagationOptions::default(),
    )
    .unwrap();
    assert_eq!(weighted.communities(), [0, 1, 0, 3]);

    assert!(matches!(
        label_propagation(
            &graph(1, &[], None, Orientation::Undirected, &context),
            LabelPropagationOptions {
                max_iterations: 0,
                seed: None
            }
        ),
        Err(AlgorithmError::InvalidArguments(_))
    ));
}

fn scrambled(n: usize, edges: usize) -> Vec<(usize, usize)> {
    let mut random = Xorshift(0x9E37_79B9_7F4A_7C15);
    (0..edges)
        .map(|_| (random.below(n), random.below(n).pow(2) / n))
        .collect()
}

#[test]
fn a_seed_reproduces_its_result_at_any_pool_width() {
    let edges = scrambled(2000, 6000);
    let run = |threads: usize, seed| {
        let context = context().with_concurrency(threads).unwrap();
        let projection = graph(2000, &edges, None, Orientation::Undirected, &context);
        let before = context.usage().unwrap().work_units;
        let result = label_propagation(
            &projection,
            LabelPropagationOptions {
                max_iterations: 50,
                seed,
            },
        )
        .unwrap();
        (
            result.communities().to_vec(),
            context.usage().unwrap().work_units - before,
        )
    };
    let first = run(1, Some(7));
    assert_eq!(run(8, Some(7)), first);
    assert_ne!(run(1, Some(8)).0, first.0, "another seed, another order");
    assert_eq!(run(1, None), run(3, None));
}

#[test]
fn label_propagation_observes_cancellation_and_budget_and_releases_scratch() {
    let edges = scrambled(2000, 20_000);
    let context = context();
    let projection = graph(2000, &edges, None, Orientation::Outgoing, &context);
    let projection_work = context.usage().unwrap().work_units;
    context.cancel().unwrap();
    assert!(matches!(
        label_propagation(&projection, LabelPropagationOptions::default()),
        Err(AlgorithmError::Cancelled)
    ));

    let tight = ExecutionContext::new(limits(2 * projection_work + 30_000)).unwrap();
    let projection = graph(2000, &edges, None, Orientation::Outgoing, &tight);
    assert!(matches!(
        label_propagation(&projection, LabelPropagationOptions::default()),
        Err(AlgorithmError::BudgetExceeded {
            resource: "work",
            ..
        })
    ));
    // The in-arcs a directed run builds stay with the projection; scratch does not.
    drop(projection);
    assert_eq!(tight.usage().unwrap().live_bytes, 0);
}

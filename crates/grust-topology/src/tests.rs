use super::*;

struct Graph {
    offsets: Vec<usize>,
    targets: Vec<usize>,
}

impl DirectedGraph for Graph {
    fn node_count(&self) -> usize {
        self.offsets.len() - 1
    }
    fn outgoing(&self, node: usize) -> Range<usize> {
        self.offsets[node]..self.offsets[node + 1]
    }
    fn target(&self, arc: usize) -> usize {
        self.targets[arc]
    }
}

fn sort(graph: &Graph, limit: usize) -> Result<(Outcome, Vec<usize>), &'static str> {
    let n = graph.node_count();
    let mut visits = vec![Visit::Unseen; n];
    let mut order = Vec::with_capacity(n);
    let mut stack = Vec::with_capacity(n);
    let mut work = 0;
    let outcome = topological_sort(
        graph,
        Scratch {
            visits: &mut visits,
            order: &mut order,
            stack: &mut stack,
        },
        |cost| {
            work += cost;
            if work > limit {
                Err("cancelled")
            } else {
                Ok(())
            }
        },
    )?;
    if let Outcome::Cycle { entry } = outcome {
        order = stack
            .iter()
            .skip_while(|(node, _)| *node != entry)
            .map(|(node, _)| *node)
            .chain([entry])
            .collect();
    }
    Ok((outcome, order))
}

#[test]
fn diamond_and_disconnected_node() {
    let graph = Graph {
        offsets: vec![0, 2, 3, 4, 4, 4],
        targets: vec![1, 2, 3, 3],
    };
    let (outcome, order) = sort(&graph, usize::MAX).unwrap();
    assert_eq!(outcome, Outcome::Acyclic);
    assert_eq!(order.len(), 5);
    for node in 0..graph.node_count() {
        for arc in graph.outgoing(node) {
            assert!(
                order.iter().position(|x| *x == node).unwrap()
                    < order.iter().position(|x| *x == graph.target(arc)).unwrap()
            );
        }
    }
}

#[test]
fn cycle_witness_excludes_acyclic_prefix() {
    let graph = Graph {
        offsets: vec![0, 1, 2, 3, 4],
        targets: vec![1, 2, 3, 1],
    };
    assert_eq!(
        sort(&graph, usize::MAX),
        Ok((Outcome::Cycle { entry: 1 }, vec![1, 2, 3, 1]))
    );
}

#[test]
fn self_loop_and_empty_graph() {
    assert_eq!(
        sort(
            &Graph {
                offsets: vec![0, 1],
                targets: vec![0]
            },
            usize::MAX
        ),
        Ok((Outcome::Cycle { entry: 0 }, vec![0, 0]))
    );
    assert_eq!(
        sort(
            &Graph {
                offsets: vec![0],
                targets: vec![]
            },
            usize::MAX
        ),
        Ok((Outcome::Acyclic, vec![]))
    );
}

#[test]
fn cancellation_is_returned_without_successful_partial_order() {
    let graph = Graph {
        offsets: vec![0, 1, 2, 2],
        targets: vec![1, 2],
    };
    assert_eq!(sort(&graph, 2), Err("cancelled"));
}

#[test]
fn long_chain_does_not_recurse() {
    let n = 100_000;
    let graph = Graph {
        offsets: (0..n).chain([n - 1]).collect(),
        targets: (1..n).collect(),
    };
    assert_eq!(
        sort(&graph, usize::MAX),
        Ok((Outcome::Acyclic, (0..n).collect()))
    );
}

#[test]
fn every_three_vertex_graph_matches_independent_removal_oracle() {
    for bits in 0u16..512 {
        let mut graph = Graph {
            offsets: vec![0],
            targets: vec![],
        };
        let mut incoming = [0; 3];
        for source in 0..3 {
            for (target, count) in incoming.iter_mut().enumerate() {
                if bits & (1 << (source * 3 + target)) != 0 {
                    graph.targets.push(target);
                    *count += 1;
                }
            }
            graph.offsets.push(graph.targets.len());
        }
        let mut removed = [false; 3];
        while let Some(node) = (0..3).find(|&n| !removed[n] && incoming[n] == 0) {
            removed[node] = true;
            for arc in graph.outgoing(node) {
                incoming[graph.target(arc)] -= 1;
            }
        }
        let (outcome, values) = sort(&graph, usize::MAX).unwrap();
        assert_eq!(
            outcome == Outcome::Acyclic,
            removed.iter().all(|x| *x),
            "{bits}"
        );
        if matches!(outcome, Outcome::Cycle { .. }) {
            assert!(values.len() >= 2);
            assert_eq!(values.first(), values.last());
            for edge in values.windows(2) {
                assert!(
                    graph
                        .outgoing(edge[0])
                        .any(|arc| graph.target(arc) == edge[1])
                );
            }
        } else {
            let mut seen = [false; 3];
            for node in values {
                assert!(!seen[node]);
                seen[node] = true;
                for arc in graph.outgoing(node) {
                    assert!(!seen[graph.target(arc)]);
                }
            }
            assert!(seen.iter().all(|x| *x));
        }
    }
}

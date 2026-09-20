//! k-core against its definition, exhaustively over small multigraphs.

use grust_algorithms::{
    AlgorithmError as ProcedureError, ExecutionContext, ExecutionLimits, GraphProjection,
    Orientation, ProjectionEdge, SnapshotIdentity, k_core,
};

fn context() -> ExecutionContext {
    ExecutionContext::new(ExecutionLimits {
        memory_bytes: 8 * 1024 * 1024,
        work_units: 10_000_000,
        batch_rows: 1024,
        deadline: None,
    })
    .unwrap()
}

fn graph(
    n: usize,
    edges: &[(usize, usize)],
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
        None,
        orientation,
        context,
    )
    .unwrap()
}

/// The definition, applied directly: the k-core is what survives repeatedly
/// deleting nodes whose degree (parallel edges counted, loops not) is below k.
fn cores_by_definition(n: usize, edges: &[(usize, usize)]) -> Vec<i64> {
    let mut core = vec![0i64; n];
    for k in 1..=edges.len() as i64 {
        let mut alive = vec![true; n];
        loop {
            let mut removed = false;
            for v in 0..n {
                if !alive[v] {
                    continue;
                }
                let degree = edges
                    .iter()
                    .filter(|&&(a, b)| a != b && alive[a] && alive[b] && (a == v || b == v))
                    .count() as i64;
                if degree < k {
                    alive[v] = false;
                    removed = true;
                }
            }
            if !removed {
                break;
            }
        }
        if !alive.iter().any(|&a| a) {
            break;
        }
        for v in 0..n {
            if alive[v] {
                core[v] = k;
            }
        }
    }
    core
}

#[test]
fn k_core_matches_an_independent_oracle() {
    // Every multigraph on four nodes with multiplicity 0, 1 or 2 per pair, with
    // and without a loop on every node: 3^6 * 2 = 1458 graphs.
    let pairs = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)];
    for code in 0..3usize.pow(6) {
        for loops in [false, true] {
            let mut edges = Vec::new();
            let mut rest = code;
            for &pair in &pairs {
                for _ in 0..rest % 3 {
                    edges.push(pair);
                }
                rest /= 3;
            }
            if loops {
                edges.extend((0..4).map(|v| (v, v)));
            }
            let context = context();
            let result = k_core(&graph(4, &edges, Orientation::Undirected, &context)).unwrap();
            let expected = cores_by_definition(4, &edges);
            assert_eq!(result.core_values(), expected, "edges {edges:?}");
            assert_eq!(result.degeneracy(), *expected.iter().max().unwrap());
        }
    }
    // Every simple graph on five nodes: 2^10.
    let pairs: Vec<(usize, usize)> = (0..5)
        .flat_map(|a| (a + 1..5).map(move |b| (a, b)))
        .collect();
    for code in 0..1usize << pairs.len() {
        let edges: Vec<_> = pairs
            .iter()
            .enumerate()
            .filter(|(bit, _)| code >> bit & 1 == 1)
            .map(|(_, &pair)| pair)
            .collect();
        let context = context();
        let result = k_core(&graph(5, &edges, Orientation::Undirected, &context)).unwrap();
        assert_eq!(
            result.core_values(),
            cores_by_definition(5, &edges),
            "{edges:?}"
        );
    }
}

#[test]
fn k_core_states_multigraph_and_self_loop_semantics() {
    let context = context();
    // Three parallel edges make a 3-core of two nodes.
    let parallel = k_core(&graph(
        2,
        &[(0, 1), (0, 1), (1, 0)],
        Orientation::Undirected,
        &context,
    ))
    .unwrap();
    assert_eq!(parallel.core_values(), [3, 3]);
    // Loops never help: a node with only loops has core 0, and a loop on a
    // triangle's corner leaves the triangle a 2-core.
    let loops = k_core(&graph(
        4,
        &[(0, 0), (0, 0), (1, 2), (2, 3), (3, 1), (1, 1)],
        Orientation::Undirected,
        &context,
    ))
    .unwrap();
    assert_eq!(loops.core_values(), [0, 2, 2, 2]);
}

#[test]
fn k_core_handles_empty_single_node_and_isolates() {
    let context = context();
    let empty = k_core(&graph(0, &[], Orientation::Undirected, &context)).unwrap();
    assert!(empty.core_values().is_empty());
    assert_eq!(empty.degeneracy(), 0);
    let single = k_core(&graph(1, &[], Orientation::Undirected, &context)).unwrap();
    assert_eq!(single.core_values(), [0]);
    // A pendant path off a 4-clique, plus an isolate.
    let edges = [
        (0, 1),
        (0, 2),
        (0, 3),
        (1, 2),
        (1, 3),
        (2, 3),
        (3, 4),
        (4, 5),
    ];
    let mixed = k_core(&graph(7, &edges, Orientation::Undirected, &context)).unwrap();
    assert_eq!(mixed.core_values(), [3, 3, 3, 3, 1, 1, 0]);
    assert_eq!(mixed.degeneracy(), 3);
}

#[test]
fn k_core_rejects_directed_projections_without_leaking_admission() {
    for orientation in [Orientation::Outgoing, Orientation::Incoming] {
        let context = context();
        let projection = graph(3, &[(0, 1), (1, 2)], orientation, &context);
        let held = context.usage().unwrap().live_bytes;
        assert!(matches!(
            k_core(&projection),
            Err(ProcedureError::InvalidArguments(message)) if message.contains("undirected")
        ));
        assert_eq!(context.usage().unwrap().live_bytes, held);
    }
}

#[test]
fn k_core_observes_cancellation_and_budget_and_releases_scratch() {
    let edges: Vec<(usize, usize)> = (0..4000).map(|i| (i, i + 1)).collect();

    let context = context();
    let projection = graph(4001, &edges, Orientation::Undirected, &context);
    let held = context.usage().unwrap().live_bytes;
    context.cancel().unwrap();
    assert!(matches!(
        k_core(&projection),
        Err(ProcedureError::Cancelled)
    ));
    assert_eq!(context.usage().unwrap().live_bytes, held);

    // A budget that admits the projection but not the whole peel fails inside
    // the kernel. The projection's own cost is measured, not guessed.
    let projection_work = context.usage().unwrap().work_units;
    let tight = ExecutionContext::new(ExecutionLimits {
        memory_bytes: 8 * 1024 * 1024,
        work_units: projection_work + 3000,
        batch_rows: 1024,
        deadline: None,
    })
    .unwrap();
    let projection = graph(4001, &edges, Orientation::Undirected, &tight);
    let held = tight.usage().unwrap().live_bytes;
    assert!(matches!(
        k_core(&projection),
        Err(ProcedureError::BudgetExceeded {
            resource: "work",
            ..
        })
    ));
    assert_eq!(tight.usage().unwrap().live_bytes, held);
}

#[cfg(feature = "arrow")]
#[test]
fn k_core_arrow_batches_keep_bounds_and_admission() {
    use arrow_array::{Array, Int64Array, StringArray};
    let context = ExecutionContext::new(ExecutionLimits {
        memory_bytes: 8 * 1024 * 1024,
        work_units: 1_000_000,
        batch_rows: 2,
        deadline: None,
    })
    .unwrap();
    let edges = [(0, 1), (1, 2), (2, 0), (2, 3)];
    let projection = graph(5, &edges, Orientation::Undirected, &context);
    let mut cursor = k_core(&projection)
        .unwrap()
        .into_table()
        .into_arrow_results();
    drop(projection);

    let mut ids = Vec::new();
    let mut cores = Vec::new();
    let mut retained = Vec::new();
    while let Some(batch) = cursor.next_batch().unwrap() {
        let record = batch.record_batch();
        assert!(record.num_rows() <= 2);
        let names: Vec<_> = record
            .schema()
            .fields()
            .iter()
            .map(|f| f.name().clone())
            .collect();
        assert_eq!(names, ["nodeId", "coreValue", "degeneracy"]);
        let id = record
            .column(0)
            .as_any()
            .downcast_ref::<StringArray>()
            .unwrap();
        let core = record
            .column(1)
            .as_any()
            .downcast_ref::<Int64Array>()
            .unwrap();
        let degeneracy = record
            .column(2)
            .as_any()
            .downcast_ref::<Int64Array>()
            .unwrap();
        for row in 0..record.num_rows() {
            ids.push(id.value(row).to_string());
            cores.push(core.value(row));
            assert_eq!(degeneracy.value(row), 2);
        }
        assert!(batch.reserved_bytes() > 0);
        retained.push(batch);
    }
    assert_eq!(ids, ["n0", "n1", "n2", "n3", "n4"]);
    assert_eq!(cores, [2, 2, 2, 1, 0]);
    // Retained batches keep their admission after the cursor is gone.
    drop(cursor);
    let live = context.usage().unwrap().live_bytes;
    assert!(live >= retained.iter().map(|b| b.reserved_bytes()).sum::<usize>());
    drop(retained);
    assert_eq!(context.usage().unwrap().live_bytes, 0);
}

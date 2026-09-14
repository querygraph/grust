//! Prepared-projection kernel costs; capture, projection and Arrow output excluded.
use criterion::{BenchmarkId, Criterion, Throughput, criterion_group, criterion_main};
use grust_algorithms::{
    ExecutionContext, ExecutionLimits, GraphProjection, Orientation, ProjectionEdge,
    SnapshotIdentity, degree,
};
use std::hint::black_box;

fn projection(nodes: usize, weighted: bool) -> GraphProjection {
    let active = nodes - nodes / 10;
    let edges = (0..active)
        .flat_map(|source| {
            (0..8).map(move |step| ProjectionEdge {
                source,
                target: (source + step) % active,
                ordinal: source * 8 + step,
                id: None,
            })
        })
        .collect::<Vec<_>>();
    let weights = weighted.then(|| (0..edges.len()).map(|edge| (edge % 8) as f64).collect());
    let context = ExecutionContext::new(ExecutionLimits {
        memory_bytes: 256 << 20,
        work_units: usize::MAX,
        batch_rows: 4096,
        deadline: None,
    })
    .unwrap();
    GraphProjection::from_topology(
        SnapshotIdentity::new("degree-bench".into(), "fixture-v1".into(), "reader".into()).unwrap(),
        (0..nodes).map(|id| id.to_string().into()).collect(),
        edges,
        weights,
        Orientation::Outgoing,
        &context,
    )
    .unwrap()
}

fn benchmarks(c: &mut Criterion) {
    let mut group = c.benchmark_group("prepared_degree");
    group.sample_size(20);
    for nodes in [4096, 65536] {
        for weighted in [false, true] {
            let graph = projection(nodes, weighted);
            let active = nodes - nodes / 10;
            // Closed-form fixture oracle, independent of the CSR offsets.
            let result = degree(&graph).unwrap();
            for node in 0..nodes {
                assert_eq!(result.counts()[node], if node < active { 8 } else { 0 });
                if let Some(strengths) = result.strengths() {
                    assert_eq!(strengths[node], if node < active { 28.0 } else { 0.0 });
                }
            }
            drop(result);
            let retained = graph.execution().usage().unwrap().live_bytes;
            group.throughput(Throughput::Elements(nodes as u64));
            group.bench_function(
                BenchmarkId::new(if weighted { "weighted" } else { "unweighted" }, nodes),
                |b| b.iter(|| black_box(degree(black_box(&graph)).unwrap())),
            );
            assert_eq!(graph.execution().usage().unwrap().live_bytes, retained);
        }
    }
    group.finish();
}
criterion_group!(benches, benchmarks);
criterion_main!(benches);

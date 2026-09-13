//! Direct graph analytics with explicit identity, options and resource ownership.
use grust_algorithms::*;
use grust_core::{Edge, Graph, Node, Props, Value};
use std::ops::ControlFlow;

fn main() -> std::result::Result<(), Box<dyn std::error::Error>> {
    let graph = Graph::new(
        ["start", "middle", "finish", "isolate"]
            .map(|id| Node::new("Place", id, Props::new()))
            .into(),
        vec![
            Edge::new(
                "ROAD",
                "start",
                "middle",
                [("cost".into(), Value::Float(2.0))],
            )
            .with_id("road-one"),
            Edge::new(
                "ROAD",
                "middle",
                "finish",
                [("cost".into(), Value::Float(0.5))],
            )
            .with_id("road-two"),
        ],
    );
    // The caller admits this input graph separately from the algorithm working set.
    let context = ExecutionContext::new(ExecutionLimits {
        memory_bytes: 1024 * 1024,
        work_units: 100_000,
        batch_rows: 64,
        deadline: None,
    })?;
    let projection = GraphProjection::from_graph(
        &graph,
        SnapshotIdentity::new("roads".into(), "revision-1".into(), "reader".into())?,
        ProjectionOptions {
            weight: WeightSelection::Property {
                key: "cost",
                missing: MissingWeight::Reject,
            },
            ..Default::default()
        },
        &context,
    )?;
    let paths = shortest_paths(&projection, "start")?;
    assert_eq!(paths.distances().values(), &[0.0, 2.0, 2.5, f64::INFINITY]);
    let _: ControlFlow<()> = paths.visit_paths(|path| {
        // These borrowed slices are valid only during this callback.
        for (&row, &cost) in path.nodes.iter().zip(path.costs) {
            context.charge_work(1)?;
            print!("{}@{cost} ", projection.node_ids()[row]);
        }
        println!();
        Ok(ControlFlow::Continue(()))
    })?;
    Ok(())
}

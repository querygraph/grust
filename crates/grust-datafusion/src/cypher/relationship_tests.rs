use super::*;
use crate::{DataFusionEngine, ExecutionOptions, SpillPolicy};
use datafusion::arrow::array::{StringArray, UInt64Array};
use grust_arrow::{ArrowGraph, ArrowGraphTables};
use grust_core::{Edge, Graph, Node, Props};

#[tokio::test]
async fn endpoint_joins_preserve_exact_relationship_multiplicity() {
    let engine = DataFusionEngine::new(ExecutionOptions {
        working_memory_bytes: (16 * 1024 * 1024).try_into().unwrap(),
        target_partitions: 4.try_into().unwrap(),
        batch_rows: 1024.try_into().unwrap(),
        spill: SpillPolicy::Disabled,
    })
    .unwrap();
    for edges in [
        vec![],
        vec![
            Edge::new("E", "a", "b", Props::new()),
            Edge::new("E", "a", "b", Props::new()),
            Edge::new("E", "b", "b", Props::new()),
            Edge::new("E", "b", "a", Props::new()),
        ],
    ] {
        let expected = edges
            .iter()
            .enumerate()
            .map(|(ordinal, edge)| (ordinal as u64, edge.from.to_string(), edge.to.to_string()))
            .collect::<Vec<_>>();
        let graph = Graph::new(
            vec![
                Node::new("N", "a", Props::new()),
                Node::new("N", "b", Props::new()),
                Node::new("N", "isolate", Props::new()),
            ],
            edges,
        );
        let (nodes, edges) = ArrowGraph::from_graph(&graph).unwrap().into_tables();
        let snapshot =
            GraphSnapshot::try_new(&engine, ArrowGraphTables::try_new(nodes, edges).unwrap())
                .unwrap();
        let plan = snapshot
            .directed_relationships(engine.context(), "a.dotted", "r", "b")
            .unwrap();
        let bindings = plan.bindings();
        let identity = |variable: &str| CypherExpr::Function {
            name: "id".into(),
            distinct: false,
            star: false,
            args: vec![CypherExpr::Variable(variable.into())],
        };
        let parameters = CypherParameters::new();
        let expressions = vec![
            bindings.relationship_ordinal("r").unwrap().alias("ordinal"),
            lower_expression_with_bindings(&identity("a.dotted"), bindings, &parameters)
                .unwrap()
                .alias("source"),
            lower_expression_with_bindings(&identity("b"), bindings, &parameters)
                .unwrap()
                .alias("target"),
        ];
        assert_eq!(bindings.node_id("r"), Err(UnsupportedExpression::Binding));
        assert_eq!(
            bindings.relationship_ordinal("b"),
            Err(UnsupportedExpression::Binding)
        );
        let (frame, _) = plan.into_parts();
        let batches = frame.select(expressions).unwrap().collect().await.unwrap();
        let mut actual = Vec::new();
        for batch in batches {
            let ordinal = batch
                .column(0)
                .as_any()
                .downcast_ref::<UInt64Array>()
                .unwrap();
            let source = batch
                .column(1)
                .as_any()
                .downcast_ref::<StringArray>()
                .unwrap();
            let target = batch
                .column(2)
                .as_any()
                .downcast_ref::<StringArray>()
                .unwrap();
            for row in 0..batch.num_rows() {
                actual.push((
                    ordinal.value(row),
                    source.value(row).to_owned(),
                    target.value(row).to_owned(),
                ));
            }
        }
        actual.sort();
        assert_eq!(actual, expected);
        assert!(
            snapshot
                .directed_relationships(engine.context(), "a", "r", "a")
                .is_err()
        );
    }
}

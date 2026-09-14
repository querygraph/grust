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
                .directed_relationships(engine.context(), "a", "a", "b")
                .is_err()
        );
    }
}

#[tokio::test]
async fn parsed_relationship_queries_match_portable_results() {
    let engine = DataFusionEngine::new(ExecutionOptions {
        working_memory_bytes: (16 * 1024 * 1024).try_into().unwrap(),
        target_partitions: 4.try_into().unwrap(),
        batch_rows: 1024.try_into().unwrap(),
        spill: SpillPolicy::Disabled,
    })
    .unwrap();
    let mut graph = Graph::new(
        vec![
            Node::new("N", "a", Props::new()),
            Node::new("M", "b", Props::new()),
        ],
        vec![
            Edge::new("E", "a", "b", Props::new()),
            Edge::new("E", "a", "b", Props::new()),
            Edge::new("F", "b", "b", Props::new()),
            Edge::new("E", "b", "a", Props::new()),
        ],
    );
    graph.nodes[0].props.insert("x".into(), Value::Int(1));
    graph.nodes[1].props.insert("x".into(), Value::Int(2));
    graph.edges[0].props.insert("x".into(), Value::Int(7));
    graph.edges[1].props.insert("x".into(), Value::Null);
    let (nodes, edges) = ArrowGraph::from_graph(&graph).unwrap().into_tables();
    let snapshot =
        GraphSnapshot::try_new(&engine, ArrowGraphTables::try_new(nodes, edges).unwrap()).unwrap();
    let parameters = CypherParameters::from([("wanted".into(), Value::Int(7))]);
    for text in [
        "MATCH (a)-[r]->(b) RETURN count(*) AS count",
        "MATCH (a:N)-[r:E]->(b:M) RETURN count(*) AS count",
        "MATCH (a:M)<-[r:E]-(b:N) RETURN count(*) AS count",
        "MATCH (a)-[r:E|F]->(b) WHERE id(a) = 'b' RETURN count(*) AS count",
        "MATCH (a:Missing)-[r]->(b) RETURN count(*) AS count",
        "MATCH (a)-[r]->(b) RETURN id(a) AS source, count(*) AS count ORDER BY source",
        "MATCH (a)-[r]->(b) RETURN DISTINCT id(b) AS target ORDER BY target DESC SKIP 1 LIMIT 1",
        "MATCH (a)-[r]->(b) WHERE null RETURN count(*) AS count",
        "MATCH ()-->()-->() RETURN count(*) AS count",
        "MATCH ()-->()-->()-->() RETURN count(*) AS count",
        "MATCH (a)-[r]->(b)-[s]->(a) RETURN count(*) AS count",
        "MATCH ()--()--() RETURN count(*) AS count",
        "MATCH (a:N)-[r:E]->(b:M)<-[s:E]-(c:N) RETURN count(*) AS count",
        "MATCH (a {x: 1})-[r {x: 7}]->(b)-[s]->(c) WHERE id(c) = 'a' RETURN count(*) AS count",
        "MATCH (a)-[r]->(b)-[s]->(c) RETURN id(a) AS source, id(c) AS target, count(*) AS count ORDER BY source, target",
        "MATCH ()--> () RETURN count(*) AS count",
        "MATCH (:N)-[:E]->(:M) RETURN count(*) AS count",
        "MATCH ()-[r {x: 7}]->() RETURN count(r.x) AS count",
        "MATCH ()--() RETURN count(*) AS count",
        "MATCH (__grust_anonymous_1)-[]->(__grust_anonymous_1_) RETURN count(*) AS count",
        "MATCH ()-[r]->(b) WHERE id(b) = 'a' RETURN count(*) AS count",
        "MATCH (a)-[r]->(a) RETURN count(*) AS count",
        "MATCH (a)<-[r]-(a) RETURN count(*) AS count",
        "MATCH (a)-[r]-(a) RETURN count(*) AS count",
        "MATCH (a:M {x: 2})-[r:F]->(a:M) RETURN id(a) AS node, count(*) AS count",
        "MATCH (a:N)-[r]->(a:M) RETURN count(*) AS count",
        "MATCH (a)-[r]-(b) RETURN count(*) AS count",
        "MATCH (a)-[r]-(b) RETURN id(a) AS source, id(b) AS target, count(*) AS count ORDER BY source, target",
        "MATCH (a:M)-[r:F]-(b:M) RETURN count(*) AS count",
        "MATCH (a {x: 2})-[r {x: 7}]-(b {x: 1}) RETURN count(*) AS count",
        "MATCH (a {x: 1})-[r {x: $wanted}]->(b {x: 2}) RETURN count(*) AS count",
        "MATCH (b {x: 2})<-[r {x: 7}]-(a {x: 1}) RETURN count(*) AS count",
        "MATCH (a)-[r {x: null}]->(b) RETURN count(*) AS count",
        "MATCH (a)-[r {missing: 7}]->(b) RETURN count(*) AS count",
        "MATCH (a {x: 2})-[r]->(b {x: 2}) RETURN count(*) AS count",
    ] {
        let query = grust_cypher::parser::parse_query(text).unwrap();
        let expected = grust_cypher::read::execute_read_query(&graph, &query, &parameters).unwrap();
        let NodeScanPlan::Supported(frame) =
            plan_relationship_scan(&query, &snapshot, engine.context(), &parameters).unwrap()
        else {
            panic!("unsupported: {text}");
        };
        assert_eq!(
            frame
                .schema()
                .fields()
                .iter()
                .map(|field| field.name().clone())
                .collect::<Vec<_>>(),
            expected.columns,
            "{text}"
        );
        let mut rows = Vec::new();
        for batch in frame.collect().await.unwrap() {
            let decoded = decode_result_batch(&batch).unwrap();
            assert_eq!(decoded.columns, expected.columns, "{text}");
            rows.extend(decoded.rows);
        }
        assert_eq!(rows, expected.rows, "{text}");
    }
}

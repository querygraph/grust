//! Warm-representation route costs for automatic Cypher routing.
//! One RoutedGraph is captured per size; each trial runs the complete bounded
//! read entrypoint (admission, planning, execution, portable output) on a
//! forced route. Capture time is reported once and excluded from trials.
use grust_core::{Graph, Node, Props, Value};
use grust_cypher::{CypherParameters, ReadQueryPolicy};
use grust_datafusion::{
    DataFusionEngine, ExecutionOptions, SpillPolicy,
    cypher::{ReadRoute, RouteMode, RoutedGraph},
};
use serde_json::json;
use std::{error::Error, num::NonZeroUsize, sync::Arc, time::Duration, time::Instant};

type ProfileResult<T> = Result<T, Box<dyn Error>>;
const QUERIES: &[&str] = &[
    "MATCH (n:N) WHERE n.bucket = 3 RETURN count(*) AS count LIMIT 1",
    "MATCH (n:N) WHERE n.bucket >= 14 RETURN id(n) AS id ORDER BY id LIMIT 10",
    "MATCH (n) RETURN n.bucket AS bucket, count(*) AS count ORDER BY bucket LIMIT 20",
];

#[tokio::main(flavor = "multi_thread", worker_threads = 4)]
async fn main() {
    if let Err(error) = run().await {
        println!("{}", json!({"event":"error","error":error.to_string()}));
        std::process::exit(1);
    }
}

async fn run() -> ProfileResult<()> {
    let mut args = std::env::args().skip(1);
    let repeats: usize = args.next().unwrap_or_else(|| "5".into()).parse()?;
    let sizes = args.map(|size| size.parse()).collect::<Result<Vec<usize>, _>>()?;
    let policy = ReadQueryPolicy {
        max_graph_nodes: usize::MAX,
        max_graph_edges: usize::MAX,
        max_graph_bytes: usize::MAX,
        max_candidate_work: usize::MAX,
        max_intermediate_bytes: 4 << 30,
        max_execution_time: Duration::from_secs(600),
        ..ReadQueryPolicy::default()
    };
    println!(
        "{}",
        json!({"event":"configuration","source":option_env!("GRUST_PROFILE_SOURCE"),
        "repeats":repeats,"sizes":sizes,"queries":QUERIES,
        "datafusion_working_memory_bytes":1u64 << 30,"datafusion_target_partitions":4,
        "batch_rows":8192,"spill":false,"max_intermediate_bytes":4u64 << 30,
        "boundary":"warm representations captured once per size; trial includes bounded admission, route planning, execution and portable output; both routes share one policy"})
    );
    let parameters = CypherParameters::new();
    let mut failed = false;
    for size in sizes {
        let graph = Arc::new(Graph::new(
            (0..size)
                .map(|id| {
                    Node::new(
                        if id % 2 == 0 { "N" } else { "M" },
                        id.to_string(),
                        Props::from([("bucket".into(), Value::Int((id % 16) as i64))]),
                    )
                })
                .collect(),
            vec![],
        ));
        let engine = DataFusionEngine::new(ExecutionOptions {
            working_memory_bytes: NonZeroUsize::new(1 << 30).unwrap(),
            target_partitions: NonZeroUsize::new(4).unwrap(),
            batch_rows: NonZeroUsize::new(8192).unwrap(),
            spill: SpillPolicy::Disabled,
        })?;
        let started = Instant::now();
        let routed = RoutedGraph::capture(&engine, graph)?.with_min_datafusion_nodes(0);
        println!(
            "{}",
            json!({"event":"capture","nodes":size,"seconds":started.elapsed().as_secs_f64()})
        );
        for (query_index, query) in QUERIES.iter().enumerate() {
            let mut expected = None;
            for trial in 0..repeats {
                let routes = if trial % 2 == 0 {
                    [ReadRoute::Reference, ReadRoute::DataFusion]
                } else {
                    [ReadRoute::DataFusion, ReadRoute::Reference]
                };
                for route in routes {
                    let started = Instant::now();
                    let outcome = routed
                        .run_bounded_read_query(query, &parameters, &policy, RouteMode::Force(route))
                        .await;
                    let seconds = started.elapsed().as_secs_f64();
                    let line = match outcome {
                        Ok(result) => {
                            let status = match &expected {
                                None => {
                                    expected = Some(result.table.clone());
                                    "pass"
                                }
                                Some(table) if *table == result.table => "pass",
                                Some(_) => "mismatch",
                            };
                            failed |= status != "pass";
                            json!({"event":"trial","nodes":size,"query":query_index,"route":format!("{route:?}"),
                                "trial":trial,"status":status,"seconds":seconds,"rows":result.table.rows.len()})
                        }
                        Err(error) => {
                            failed = true;
                            json!({"event":"trial","nodes":size,"query":query_index,"route":format!("{route:?}"),
                                "trial":trial,"status":"error","error":error.to_string()})
                        }
                    };
                    println!("{line}");
                }
            }
        }
    }
    if failed {
        return Err("one or more trials did not pass; all outcomes retained".into());
    }
    Ok(())
}

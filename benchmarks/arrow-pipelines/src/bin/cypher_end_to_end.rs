//! Cold-representation scan costs from one immutable row graph.
//! Each route owns and drops its prepared representation within its trial.
//! Fixture construction and teardown are outside the measured query boundary.
use grust_core::{Graph, Node, Props, TypedGraphIndex, Value};
use grust_cypher::{
    CypherParameters, CypherResultTable, parser::parse_query, read::run_read_query_indexed,
};
use grust_datafusion::{
    DataFusionEngine, ExecutionOptions, SpillPolicy,
    cypher::{collect_result, lower_node_scan},
};
use serde_json::json;
use std::{error::Error, num::NonZeroUsize, sync::Arc, time::Instant};

type ProfileResult<T> = Result<T, Box<dyn Error>>;
const QUERY: &str = "MATCH (n:N) WHERE n.bucket = 3 RETURN count(*) AS count";

#[derive(Clone, Copy, Debug)]
enum Route {
    Indexed,
    DataFusion,
}
impl Route {
    fn name(self) -> &'static str {
        match self {
            Self::Indexed => "indexed",
            Self::DataFusion => "datafusion",
        }
    }
}
struct Measurement {
    table: CypherResultTable,
    preparation_seconds: f64,
    query_seconds: f64,
}

async fn measure(route: Route, graph: &Arc<Graph>) -> ProfileResult<Option<Measurement>> {
    let started = Instant::now();
    let parameters = CypherParameters::new();
    match route {
        Route::Indexed => {
            let index = TypedGraphIndex::new(Arc::clone(graph))?;
            let preparation_seconds = started.elapsed().as_secs_f64();
            let query_started = Instant::now();
            let table = run_read_query_indexed(&index, QUERY, &parameters)?;
            Ok(Some(Measurement {
                table,
                preparation_seconds,
                query_seconds: query_started.elapsed().as_secs_f64(),
            }))
        }
        Route::DataFusion => {
            let (nodes, _) = grust_arrow::ArrowGraph::from_graph(graph)?.into_tables();
            let engine = DataFusionEngine::new(ExecutionOptions {
                working_memory_bytes: NonZeroUsize::new(256 << 20).unwrap(),
                target_partitions: NonZeroUsize::new(4).unwrap(),
                batch_rows: NonZeroUsize::new(4096).unwrap(),
                spill: SpillPolicy::Disabled,
            })?;
            engine.register_table("nodes", nodes)?;
            let preparation_seconds = started.elapsed().as_secs_f64();
            let query_started = Instant::now();
            let parsed = parse_query(QUERY).map_err(|error| format!("{error:?}"))?;
            let Some(frame) = lower_node_scan(&parsed, engine.context().table("nodes").await?)?
            else {
                return Ok(None);
            };
            let table = collect_result(frame, 1, 1024).await?;
            Ok(Some(Measurement {
                table,
                preparation_seconds,
                query_seconds: query_started.elapsed().as_secs_f64(),
            }))
        }
    }
}

#[tokio::main(flavor = "multi_thread", worker_threads = 4)]
async fn main() {
    if let Err(error) = run().await {
        println!("{}", json!({"event":"error","error":error.to_string()}));
        std::process::exit(1);
    }
}
async fn run() -> ProfileResult<()> {
    let mut args = std::env::args().skip(1);
    let nodes: usize = args.next().unwrap_or_else(|| "100000".into()).parse()?;
    let repeats: usize = args.next().unwrap_or_else(|| "3".into()).parse()?;
    if args.next().is_some() || repeats == 0 || nodes > i64::MAX as usize {
        return Err("invalid arguments".into());
    }
    println!(
        "{}",
        json!({"event":"configuration","source":env!("GRUST_PROFILE_SOURCE"),
        "nodes":nodes,"repeats":repeats,"query":QUERY,"deadline":null,
        "datafusion_working_memory_bytes":268435456,"datafusion_target_partitions":4,
        "datafusion_input_partitions":1,"datafusion_output_rows":1,"datafusion_output_bytes":1024,
        "indexed_memory_limit":null,"spill":false,
        "boundary":"row graph fixture excluded; cold representation per trial; preparation includes index or Arrow conversion and engine registration; query includes parsing, planning, execution and portable output; teardown excluded; no equivalent full resource envelope or automatic routing threshold claimed"})
    );
    let graph = Arc::new(Graph::new(
        (0..nodes)
            .map(|id| {
                Node::new(
                    "N",
                    id.to_string(),
                    Props::from([("bucket".into(), Value::Int((id % 16) as i64))]),
                )
            })
            .collect(),
        vec![],
    ));
    let expected = if nodes <= 3 { 0 } else { 1 + (nodes - 4) / 16 } as i64;
    let mut failed = false;
    for trial in 0..repeats {
        let routes = if trial % 2 == 0 {
            [Route::Indexed, Route::DataFusion]
        } else {
            [Route::DataFusion, Route::Indexed]
        };
        for route in routes {
            let outcome = match measure(route, &graph).await {
                Ok(Some(m)) => {
                    let correct = m.table.columns == ["count"]
                        && m.table.rows == vec![vec![Value::Int(expected)]];
                    failed |= !correct;
                    json!({"event":"trial","route":route.name(),"trial":trial,
                        "status":if correct {"pass"} else {"mismatch"},"expected":expected,
                        "columns":m.table.columns,"rows":m.table.rows,
                        "preparation_seconds":m.preparation_seconds,"query_seconds":m.query_seconds,
                        "total_seconds":m.preparation_seconds + m.query_seconds})
                }
                Ok(None) => {
                    failed = true;
                    json!({"event":"trial","route":route.name(),"trial":trial,"status":"unsupported"})
                }
                Err(error) => {
                    failed = true;
                    json!({"event":"trial","route":route.name(),"trial":trial,"status":"error","error":error.to_string()})
                }
            };
            println!("{outcome}");
        }
    }
    if failed {
        return Err("one or more trials did not pass; all outcomes retained".into());
    }
    Ok(())
}

//! Source-pinned fixed-path profile with a parallel-edge ring oracle; no deadline.
use grust_core::{Edge, Graph, Node, Props, TypedGraphIndex, Value};
use grust_cypher::{CypherParameters, read::run_read_query_indexed};
use grust_datafusion::{
    DataFusionEngine, ExecutionOptions, SpillPolicy,
    cypher::{CypherExecution, GraphSnapshot, OutputLimits},
};
use serde_json::json;
use std::{error::Error, sync::Arc, time::Instant};

type Result<T> = std::result::Result<T, Box<dyn Error>>;

#[tokio::main(flavor = "multi_thread", worker_threads = 4)]
async fn main() {
    if let Err(error) = run().await {
        println!("{}", json!({"event":"error","error":error.to_string()}));
        std::process::exit(1);
    }
}
async fn run() -> Result<()> {
    let mut args = std::env::args().skip(1);
    let nodes: usize = args.next().unwrap_or_else(|| "10000".into()).parse()?;
    let repeats: usize = args.next().unwrap_or_else(|| "3".into()).parse()?;
    let hops: usize = args.next().unwrap_or_else(|| "2".into()).parse()?;
    if args.next().is_some() || repeats == 0 || !matches!(hops, 2 | 3) {
        return Err("invalid arguments".into());
    }
    // Two physical edges per ring step. Small rings must exclude physical reuse.
    let expected = match (nodes, hops) {
        (0, _) => 0,
        (1, 2) => 2,
        (1, 3) => 0,
        (2, 3) => 8,
        (_, 2) => nodes.checked_mul(4).ok_or("oracle overflow")?,
        (_, 3) => nodes.checked_mul(8).ok_or("oracle overflow")?,
        _ => unreachable!(),
    };
    let expected = i64::try_from(expected)?;
    let query = format!("MATCH (){} RETURN count(*) AS count", "-->()".repeat(hops));
    println!(
        "{}",
        json!({"event":"configuration","source":env!("GRUST_PROFILE_SOURCE"),"nodes":nodes,"edges":nodes.checked_mul(2).ok_or("edge count overflow")?,"hops":hops,"repeats":repeats,"query":query,"working_memory_bytes":268435456,"partitions":4,"deadline":null,"boundary":"prepared inputs; query includes parse/plan/execute/portable consumption; DataFusion also enforces 1-row/1024-byte output; reference admission unbounded; inputs coexist outside tracked pool; preparation separately measured"})
    );
    let start = Instant::now();
    let graph = Arc::new(Graph::new(
        (0..nodes)
            .map(|id| Node::new("N", id.to_string(), Props::new()))
            .collect(),
        (0..nodes)
            .flat_map(|id| {
                (0..2).map(move |_| {
                    Edge::new(
                        "E",
                        id.to_string(),
                        ((id + 1) % nodes).to_string(),
                        Props::new(),
                    )
                })
            })
            .collect(),
    ));
    println!(
        "{}",
        json!({"event":"preparation","phase":"fixture","seconds":start.elapsed().as_secs_f64()})
    );
    let start = Instant::now();
    let index = TypedGraphIndex::new(Arc::clone(&graph))?;
    println!(
        "{}",
        json!({"event":"preparation","phase":"index","seconds":start.elapsed().as_secs_f64()})
    );
    let start = Instant::now();
    let (nodes, edges) = grust_arrow::ArrowGraph::from_graph(&graph)?.into_tables();
    let tables = grust_arrow::ArrowGraphTables::try_new(nodes, edges)?;
    let engine = DataFusionEngine::new(ExecutionOptions {
        working_memory_bytes: (256 << 20).try_into().unwrap(),
        target_partitions: 4.try_into().unwrap(),
        batch_rows: 4096.try_into().unwrap(),
        spill: SpillPolicy::Disabled,
    })?;
    let snapshot = GraphSnapshot::try_new(&engine, tables)?;
    println!(
        "{}",
        json!({"event":"preparation","phase":"arrow_snapshot_and_engine","seconds":start.elapsed().as_secs_f64()})
    );
    let mut failed = false;
    for trial in 0..repeats {
        for route in if trial % 2 == 0 {
            ["indexed", "datafusion"]
        } else {
            ["datafusion", "indexed"]
        } {
            let start = Instant::now();
            let result = execute(route, &index, &snapshot, &engine, &query).await;
            let seconds = start.elapsed().as_secs_f64();
            match result {
                Ok(Some(actual)) => {
                    failed |= actual != expected;
                    println!(
                        "{}",
                        json!({"event":"trial","route":route,"trial":trial,"seconds":seconds,"actual":actual,"expected":expected,"status":if actual==expected {"pass"} else {"mismatch"}})
                    );
                }
                Ok(None) => {
                    failed = true;
                    println!(
                        "{}",
                        json!({"event":"trial","route":route,"trial":trial,"seconds":seconds,"expected":expected,"status":"unsupported"})
                    );
                }
                Err(error) => {
                    failed = true;
                    println!(
                        "{}",
                        json!({"event":"trial","route":route,"trial":trial,"seconds":seconds,"expected":expected,"status":"error","error":error.to_string()})
                    );
                }
            }
        }
    }
    if failed {
        return Err("one or more trials failed".into());
    }
    Ok(())
}
async fn execute(
    route: &str,
    index: &TypedGraphIndex,
    snapshot: &GraphSnapshot,
    engine: &DataFusionEngine,
    query: &str,
) -> Result<Option<i64>> {
    let parameters = CypherParameters::new();
    let table = if route == "indexed" {
        run_read_query_indexed(index, query, &parameters)?
    } else {
        match snapshot
            .execute(
                query,
                engine.context(),
                &parameters,
                OutputLimits {
                    max_rows: 1,
                    max_serialized_bytes: 1024,
                },
            )
            .await?
        {
            CypherExecution::Completed { table, .. } => table,
            CypherExecution::Unsupported { .. } => return Ok(None),
        }
    };
    if table.columns != ["count"] {
        return Err("unexpected columns".into());
    }
    match table.rows.as_slice() {
        [row] => match row.as_slice() {
            [Value::Int(value)] => Ok(Some(*value)),
            _ => Err("unexpected value".into()),
        },
        _ => Err("unexpected row count".into()),
    }
}

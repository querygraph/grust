//! Source-pinned prepared-input scan profile; no query deadline.
use grust_core::{Graph, Node, Props, TypedGraphIndex, Value};
use grust_cypher::{CypherParameters, parser::parse_query, read::run_read_query_indexed};
use grust_datafusion::datafusion::arrow::array::Int64Array;
use grust_datafusion::{DataFusionEngine, ExecutionOptions, SpillPolicy, cypher::lower_node_scan};
use serde_json::json;
use std::{error::Error, num::NonZeroUsize, sync::Arc, time::Instant};

#[tokio::main(flavor = "multi_thread", worker_threads = 4)]
async fn main() {
    if let Err(error) = run().await {
        println!("{}", json!({"event":"error","error":error.to_string()}));
        std::process::exit(1);
    }
}
async fn run() -> Result<(), Box<dyn Error>> {
    let mut args = std::env::args().skip(1);
    let nodes: usize = args.next().unwrap_or_else(|| "100000".into()).parse()?;
    let repeats: usize = args.next().unwrap_or_else(|| "3".into()).parse()?;
    if args.next().is_some() || repeats == 0 || nodes > i64::MAX as usize {
        return Err("invalid arguments".into());
    }
    println!(
        "{}",
        json!({"event":"configuration","source":env!("GRUST_PROFILE_SOURCE"),"nodes":nodes,"repeats":repeats,"working_memory_bytes":268435456,"partitions":4,"deadline":null,"boundary":"prepared input; each query includes parsing/planning/execution/consumption; conversion and index separately timed; inputs coexist outside working-memory admission"})
    );
    let start = Instant::now();
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
    let (table, _) = grust_arrow::ArrowGraph::from_graph(&graph)?.into_tables();
    let engine = DataFusionEngine::new(ExecutionOptions {
        working_memory_bytes: NonZeroUsize::new(256 << 20).unwrap(),
        target_partitions: NonZeroUsize::new(4).unwrap(),
        batch_rows: NonZeroUsize::new(4096).unwrap(),
        spill: SpillPolicy::Disabled,
    })?;
    engine.register_table("nodes", table)?;
    println!(
        "{}",
        json!({"event":"preparation","phase":"arrow_and_registration","seconds":start.elapsed().as_secs_f64()})
    );
    let query = "MATCH (n:N) WHERE n.bucket = 3 RETURN count(*) AS count";
    let expected = if nodes <= 3 { 0 } else { 1 + (nodes - 4) / 16 } as i64;
    let mut mismatch = false;
    for trial in 0..repeats {
        for route in if trial % 2 == 0 {
            ["indexed", "datafusion"]
        } else {
            ["datafusion", "indexed"]
        } {
            let start = Instant::now();
            let actual = if route == "indexed" {
                let result = run_read_query_indexed(&index, query, &CypherParameters::new())?;
                match result.rows.as_slice() {
                    [row] => match row.as_slice() {
                        [Value::Int(n)] => *n,
                        _ => return Err("unexpected indexed schema".into()),
                    },
                    _ => return Err("unexpected indexed cardinality".into()),
                }
            } else {
                let parsed = parse_query(query).map_err(|e| format!("{e:?}"))?;
                let frame = lower_node_scan(&parsed, engine.context().table("nodes").await?)?
                    .ok_or("unsupported scan")?;
                let batches = frame.collect().await?;
                if batches.iter().map(|b| b.num_rows()).sum::<usize>() != 1 {
                    return Err("unexpected Arrow cardinality".into());
                }
                batches[0]
                    .column(0)
                    .as_any()
                    .downcast_ref::<Int64Array>()
                    .ok_or("unexpected Arrow type")?
                    .value(0)
            };
            let seconds = start.elapsed().as_secs_f64();
            mismatch |= actual != expected;
            println!(
                "{}",
                json!({"event":"trial","route":route,"trial":trial,"seconds":seconds,"actual":actual,"expected":expected,"status":if actual==expected {"pass"} else {"mismatch"}})
            );
        }
    }
    if mismatch {
        return Err("oracle mismatch".into());
    }
    Ok(())
}

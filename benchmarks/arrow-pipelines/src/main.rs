mod fixture;

use fixture::Workload;
use futures::TryStreamExt;
use grust_arrow::{ArrowGraph, ArrowGraphTables};
use grust_core::{GrustError, TypedGraphIndex, Value};
use grust_cypher::{CypherParameters, read::run_read_query_indexed};
use grust_datafusion::datafusion::arrow::array::{Array, Int64Array};
use grust_datafusion::{DataFusionEngine, ExecutionOptions, SpillPolicy};
use serde_json::json;
use std::{error::Error, num::NonZeroUsize, sync::Arc, time::Instant};

type Result<T> = std::result::Result<T, Box<dyn Error>>;

#[tokio::main(flavor = "multi_thread", worker_threads = 4)]
async fn main() {
    if let Err(error) = run().await {
        println!("{}", json!({"event":"error", "error":error.to_string()}));
        std::process::exit(1);
    }
}
async fn run() -> Result<()> {
    let mut args = std::env::args().skip(1);
    let nodes = argument(args.next(), 20_000)?;
    let degree = argument(args.next(), 8)?;
    let repeats = argument(args.next(), 3)?;
    if args.next().is_some() {
        return Err("usage: profile [nodes] [fanout] [repeats]".into());
    }
    // All oracle arithmetic, edge identities and property values must fit.
    let bound = (nodes as u128)
        .checked_mul(degree as u128)
        .and_then(|n| n.checked_mul(degree as u128))
        .and_then(|n| n.checked_mul(degree as u128));
    if bound.is_none_or(|n| n > i64::MAX as u128) || nodes.checked_mul(degree).is_none() {
        return Err("fixture arithmetic exceeds exact integer limits".into());
    }
    println!(
        "{}",
        json!({"event":"configuration", "source":env!("GRUST_PROFILE_SOURCE"),
        "nodes":nodes,"fanout":degree,"repeats":repeats,"datafusion_major":55,
        "working_memory_bytes":268435456,"partitions":4,
        "boundary":"local indexed Cypher and native Arrow SQL are distinct execution classes; retained input is outside working-memory accounting"})
    );
    let start = Instant::now();
    let graph = Arc::new(fixture::graph(nodes, degree));
    phase("fixture", start);
    let start = Instant::now();
    let indexed = TypedGraphIndex::new(Arc::clone(&graph))?;
    phase("typed_graph_index", start);
    let start = Instant::now();
    let (node_table, edge_table) = ArrowGraph::from_graph(&graph)?.into_tables();
    let tables = ArrowGraphTables::try_new(node_table, edge_table)?;
    phase("graph_to_arrow", start);
    let start = Instant::now();
    let engine = DataFusionEngine::new(ExecutionOptions {
        working_memory_bytes: NonZeroUsize::new(256 << 20).unwrap(),
        target_partitions: NonZeroUsize::new(4).unwrap(),
        batch_rows: NonZeroUsize::new(4096).unwrap(),
        spill: SpillPolicy::Disabled,
    })?;
    engine.register_graph("g", tables)?;
    phase("datafusion_registration", start);
    let mut failures = 0;
    for workload in Workload::ALL {
        let expected = fixture::expected(workload, nodes, degree);
        println!(
            "{}",
            json!({"event":"workload","name":workload.name(),
            "cypher":workload.cypher(),"sql":workload.sql(),"oracle":expected})
        );
        for trial in 0..repeats {
            // Alternate engine order to disclose first-use and reduce fixed order bias.
            for engine_id in if trial % 2 == 0 { [0, 1] } else { [1, 0] } {
                let started = Instant::now();
                let (name, answer) = if engine_id == 0 {
                    ("indexed_cypher", cypher(&indexed, workload))
                } else {
                    ("datafusion_sql", sql(&engine, workload).await)
                };
                let elapsed = started.elapsed().as_secs_f64();
                let (outcome, actual, error) = match answer {
                    Ok(actual) if actual == expected => ("pass", Some(actual), None),
                    Ok(actual) => ("mismatch", Some(actual), None),
                    Err(error) => {
                        let status = failure_status(error.as_ref());
                        (status, None, Some(error.to_string()))
                    }
                };
                failures += usize::from(outcome != "pass");
                println!(
                    "{}",
                    json!({"event":"result","workload":workload.name(),
                    "engine":name,"trial":trial,"seconds":elapsed,"outcome":outcome,
                    "actual":actual,"expected":expected,"error":error})
                );
            }
        }
    }
    println!("{}", json!({"event":"completion","failures":failures}));
    if failures > 0 {
        return Err("one or more profiles did not pass the independent oracle".into());
    }
    Ok(())
}
fn argument(value: Option<String>, default: usize) -> Result<usize> {
    let value = value.map(|s| s.parse::<NonZeroUsize>()).transpose()?;
    Ok(value.map_or(default, NonZeroUsize::get))
}
fn phase(name: &str, started: Instant) {
    println!(
        "{}",
        json!({"event":"preparation","phase":name,"seconds":started.elapsed().as_secs_f64()})
    );
}
fn cypher(index: &TypedGraphIndex, workload: Workload) -> Result<(i64, i64)> {
    let table = run_read_query_indexed(index, workload.cypher(), &CypherParameters::new())?;
    match table.rows.as_slice() {
        [row] => match row.as_slice() {
            [Value::Int(count), Value::Int(sum)] => Ok((*count, *sum)),
            _ => Err(format!("unexpected Cypher result: {table:?}").into()),
        },
        _ => Err(format!("unexpected Cypher row count: {}", table.rows.len()).into()),
    }
}
async fn sql(engine: &DataFusionEngine, workload: Workload) -> Result<(i64, i64)> {
    let mut stream = engine.execute_stream(workload.sql()).await?;
    let mut answer = None;
    while let Some(batch) = stream.try_next().await? {
        if batch.num_columns() != 2 {
            return Err("unexpected SQL column count".into());
        }
        let a = batch
            .column(0)
            .as_any()
            .downcast_ref::<Int64Array>()
            .ok_or("SQL count is not Int64")?;
        let b = batch
            .column(1)
            .as_any()
            .downcast_ref::<Int64Array>()
            .ok_or("SQL sum is not Int64")?;
        for i in 0..batch.num_rows() {
            if answer.is_some() || a.is_null(i) || b.is_null(i) {
                return Err("unexpected SQL row or null".into());
            }
            answer = Some((a.value(i), b.value(i)));
        }
    }
    answer.ok_or_else(|| "SQL aggregate returned no row".into())
}

fn failure_status(mut error: &(dyn Error + 'static)) -> &'static str {
    use grust_datafusion::datafusion::common::DataFusionError;
    loop {
        match error.downcast_ref::<GrustError>() {
            Some(GrustError::Unsupported(_) | GrustError::CypherUnsupportedCardinality(_)) => {
                return "unsupported";
            }
            Some(GrustError::ResourceLimitExceeded { .. }) => return "resource_exhausted",
            _ => {}
        }
        match error.downcast_ref::<DataFusionError>() {
            Some(DataFusionError::NotImplemented(_)) => return "unsupported",
            Some(DataFusionError::ResourcesExhausted(_)) => return "resource_exhausted",
            _ => {}
        }
        match error.source() {
            Some(source) => error = source,
            None => return "error",
        }
    }
}

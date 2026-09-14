//! Diagnostic execution with physical-plan and memory metadata; no timing claim.
use grust_core::{Graph, Node, Props, Value};
use grust_cypher::parser::parse_query;
use grust_datafusion::{
    DataFusionEngine, ExecutionOptions, SpillPolicy,
    cypher::lower_node_scan,
    datafusion::physical_plan::{collect, displayable},
};
use serde_json::json;
use std::{error::Error, num::NonZeroUsize};

#[tokio::main(flavor = "multi_thread", worker_threads = 4)]
async fn main() -> Result<(), Box<dyn Error>> {
    let mut args = std::env::args().skip(1);
    let nodes: usize = args.next().unwrap_or_else(|| "1000000".into()).parse()?;
    let partitions: NonZeroUsize = args.next().unwrap_or_else(|| "4".into()).parse()?;
    let repeats: usize = args.next().unwrap_or_else(|| "10".into()).parse()?;
    if args.next().is_some() || repeats == 0 || nodes > i64::MAX as usize {
        return Err("invalid arguments".into());
    }
    let graph = Graph::new(
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
    );
    let expected = if nodes <= 3 { 0 } else { 1 + (nodes - 4) / 16 } as i64;
    let mut failed = false;
    for trial in 0..repeats {
        let arrow = grust_arrow::ArrowGraph::from_graph(&graph)?;
        let batch = arrow.nodes();
        println!(
            "{}",
            json!({"event":"input","source":env!("GRUST_PROFILE_SOURCE"),
            "trial":trial,"rows":nodes,"partitions":partitions.get(),"pool_bytes":256<<20,
            "batch_bytes":batch.get_array_memory_size(),
            "slice_4096_bytes":batch.slice(0, nodes.min(4096)).get_array_memory_size()})
        );
        let (nodes, _) = arrow.into_tables();
        let engine = DataFusionEngine::new(ExecutionOptions {
            working_memory_bytes: NonZeroUsize::new(256 << 20).unwrap(),
            target_partitions: partitions,
            batch_rows: NonZeroUsize::new(4096).unwrap(),
            spill: SpillPolicy::Disabled,
        })?;
        engine.register_table("nodes", nodes)?;
        let query = parse_query("MATCH (n:N) WHERE n.bucket = 3 RETURN count(*) AS count")
            .map_err(|e| format!("{e:?}"))?;
        let frame = lower_node_scan(&query, engine.context().table("nodes").await?)?
            .ok_or("unsupported diagnostic query")?;
        let plan = frame.create_physical_plan().await?;
        println!(
            "{}",
            json!({"event":"plan","trial":trial,
            "plan":displayable(plan.as_ref()).indent(true).to_string()})
        );
        let result = collect(plan, engine.context().task_ctx()).await;
        match result {
            Ok(batches) => {
                let mut rows = Vec::new();
                for batch in batches {
                    rows.extend(grust_datafusion::cypher::decode_result_batch(&batch)?.rows);
                }
                let pass = rows == vec![vec![Value::Int(expected)]];
                failed |= !pass;
                println!(
                    "{}",
                    json!({"event":"result","trial":trial,"status":if pass {"pass"} else {"mismatch"},"rows":rows})
                );
            }
            Err(error) => {
                failed = true;
                println!(
                    "{}",
                    json!({"event":"result","trial":trial,"status":"error","error":error.to_string()})
                );
            }
        }
    }
    if failed {
        return Err("diagnostic failures retained".into());
    }
    Ok(())
}

//! Run Grust's algorithms inside a Sail server that has the `nutmeg` data
//! source, on the Grust graph stored there. The rows never leave the server
//! until the result.
//!
//!     SAIL_ENDPOINT=http://127.0.0.1:50051 cargo run -p grust-sail --example server_algorithms
use std::io::Cursor;

use arrow::ipc::reader::StreamReader;
use arrow::util::display::array_value_to_string;
use grust_core::prelude::{Edge, GraphAdminStore, GraphStore, Node, Props, Value};
use grust_sail::{SailConfig, SailGraphStore, SailWarehouse};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let endpoint =
        std::env::var("SAIL_ENDPOINT").unwrap_or_else(|_| "http://127.0.0.1:50051".to_string());
    let store = SailGraphStore::connect(SailConfig {
        endpoint,
        warehouse: SailWarehouse::LocalSessionScoped,
        ..SailConfig::default()
    })
    .await?;
    store.bootstrap().await?;
    // The ordinary GraphStore API: nothing here is algorithm-specific.
    for id in ["a", "b", "c"] {
        store
            .put_node(&Node::new("Person", id, Props::new()))
            .await?;
    }
    for (source, target, weight) in [
        ("a", "b", 1.0),
        ("b", "c", 2.0),
        ("c", "a", 3.0),
        ("a", "c", 10.0),
    ] {
        let mut props = Props::new();
        props.insert("weight".into(), Value::from(weight));
        store
            .put_edge(&Edge::new("KNOWS", source, target, props))
            .await?;
    }
    store.stage_algorithm_graph("people", &["weight"]).await?;
    let mut configuration = serde_json::Map::new();
    configuration.insert("damping".into(), serde_json::json!(0.9));
    let mut dijkstra = serde_json::Map::new();
    dijkstra.insert("source".into(), serde_json::json!("a"));
    dijkstra.insert("weightProperty".into(), serde_json::json!("weight"));
    for (algorithm, configuration) in [
        ("projectionStats", serde_json::Map::new()),
        ("pagerank", configuration),
        ("wcc", serde_json::Map::new()),
        ("dijkstra", dijkstra),
    ] {
        println!("{algorithm}");
        for stream in store
            .run_algorithm("people", algorithm, &configuration)
            .await?
        {
            for batch in StreamReader::try_new(Cursor::new(stream), None)? {
                let batch = batch?;
                for row in 0..batch.num_rows() {
                    let cells: Vec<String> = batch
                        .schema()
                        .fields()
                        .iter()
                        .zip(batch.columns())
                        .map(|(field, column)| {
                            Ok(format!(
                                "{}={}",
                                field.name(),
                                array_value_to_string(column, row)?
                            ))
                        })
                        .collect::<Result<_, arrow::error::ArrowError>>()?;
                    println!("  {}", cells.join("  "));
                }
            }
        }
    }
    Ok(())
}

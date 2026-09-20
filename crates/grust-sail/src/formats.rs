//! Spark data source formats through Sail, and server-side graph algorithms.
//!
//! Two layers. The first is general Spark Connect: read any registered data
//! source format with options, and write the result of a query to one —
//! what PySpark spells `spark.read.format(f).options(o).load()` and
//! `spark.sql(q).write.format(f).options(o).mode(m).save()`.
//!
//! The second uses the first to run graph algorithms where the graph is
//! stored. A Sail server with the `nutmeg` data source runs Grust's
//! algorithm kernels in the server process: [`SailGraphStore::stage_algorithm_graph`]
//! projects `grust_nodes`/`grust_edges` into a named in-server graph without
//! the rows leaving Sail, and [`SailGraphStore::run_algorithm`] returns one
//! algorithm's result as Arrow. The configuration map is the one Grust's
//! algorithm procedures take (`orientation`, `weightProperty`, `damping`, …)
//! and is validated on the server by the same validator.
use std::collections::HashMap;

use grust_core::{GrustError, Result};

use super::sc::{
    self, Command, Plan, Read, Relation, WriteOperation, command, plan, read, relation,
};
use super::{
    EDGE_DST_ID_COLUMN, EDGE_ID_COLUMN, EDGE_PROPS_COLUMN, EDGE_SRC_ID_COLUMN, EDGE_TYPE_COLUMN,
    GRUST_EDGES_TABLE, GRUST_NODES_TABLE, NODE_ID_COLUMN, NODE_LABEL_COLUMN, SailGraphStore,
    sail_json_property_expr,
};

/// The data source format a Sail server registers for Grust's algorithms.
pub const SAIL_ALGORITHMS_FORMAT: &str = "nutmeg";

/// Spark's save modes.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SailSaveMode {
    Append,
    Overwrite,
    ErrorIfExists,
    Ignore,
}

impl SailSaveMode {
    fn proto(self) -> sc::write_operation::SaveMode {
        use sc::write_operation::SaveMode;
        match self {
            Self::Append => SaveMode::Append,
            Self::Overwrite => SaveMode::Overwrite,
            Self::ErrorIfExists => SaveMode::ErrorIfExists,
            Self::Ignore => SaveMode::Ignore,
        }
    }
}

/// `SELECT` over `grust_nodes` in the grust-arrow node layout.
pub fn sail_algorithm_nodes_sql() -> String {
    format!(
        "SELECT {NODE_ID_COLUMN} AS node_id, {NODE_LABEL_COLUMN} AS label FROM {GRUST_NODES_TABLE}"
    )
}

/// `SELECT` over `grust_edges` in the grust-arrow edge layout, with each
/// named numeric property lifted out of the JSON `props` column as a DOUBLE
/// column of the same name (null where the edge lacks it).
pub fn sail_algorithm_edges_sql(weight_properties: &[&str]) -> Result<String> {
    let mut columns = format!(
        "{EDGE_ID_COLUMN} AS edge_id, {EDGE_SRC_ID_COLUMN} AS source, \
         {EDGE_DST_ID_COLUMN} AS target, {EDGE_TYPE_COLUMN} AS label"
    );
    for key in weight_properties {
        if !key.chars().all(|c| c.is_ascii_alphanumeric() || c == '_') || key.is_empty() {
            return Err(GrustError::Backend(format!(
                "weight property `{key}` must be an identifier"
            )));
        }
        let value = sail_json_property_expr(EDGE_PROPS_COLUMN, key)?;
        columns.push_str(&format!(", CAST({value} AS DOUBLE) AS {key}"));
    }
    Ok(format!("SELECT {columns} FROM {GRUST_EDGES_TABLE}"))
}

impl SailGraphStore {
    /// Reads a Spark data source format with options; each item is one Arrow
    /// IPC stream, as from [`Self::query_arrow_ipc`].
    pub async fn read_format_arrow_ipc(
        &self,
        format: &str,
        options: HashMap<String, String>,
    ) -> Result<Vec<Vec<u8>>> {
        let request = self.request_with_plan(Plan {
            op_type: Some(plan::OpType::Root(Relation {
                common: None,
                rel_type: Some(relation::RelType::Read(Read {
                    is_streaming: false,
                    read_type: Some(read::ReadType::DataSource(read::DataSource {
                        format: Some(format.to_string()),
                        options,
                        ..Default::default()
                    })),
                })),
            })),
        });
        let mut chunks = Vec::new();
        self.run_plan(request, |data| {
            chunks.push(data);
            Ok(())
        })
        .await?;
        Ok(chunks)
    }

    /// Writes the rows of a Spark SQL query to a data source format.
    pub async fn write_query_to_format(
        &self,
        sql: &str,
        format: &str,
        mode: SailSaveMode,
        options: HashMap<String, String>,
    ) -> Result<()> {
        let input = Relation {
            common: None,
            rel_type: Some(relation::RelType::Sql(sc::Sql {
                query: sql.to_string(),
                ..Default::default()
            })),
        };
        let request = self.request_with_plan(Plan {
            op_type: Some(plan::OpType::Command(Command {
                command_type: Some(command::CommandType::WriteOperation(WriteOperation {
                    input: Some(input),
                    source: Some(format.to_string()),
                    mode: mode.proto() as i32,
                    options,
                    ..Default::default()
                })),
            })),
        });
        self.run_plan(request, |_| Ok(())).await
    }

    /// Projects the stored Grust graph into the server's algorithm engine
    /// under `graph`, replacing any earlier staging of that name. The rows go
    /// from Sail's tables to the engine inside the server. Each name in
    /// `weight_properties` becomes selectable as `weightProperty`.
    pub async fn stage_algorithm_graph(
        &self,
        graph: &str,
        weight_properties: &[&str],
    ) -> Result<()> {
        for (part, sql) in [
            ("nodes", sail_algorithm_nodes_sql()),
            ("edges", sail_algorithm_edges_sql(weight_properties)?),
        ] {
            let options = HashMap::from([
                ("graph".to_string(), graph.to_string()),
                ("part".to_string(), part.to_string()),
            ]);
            self.write_query_to_format(
                &sql,
                SAIL_ALGORITHMS_FORMAT,
                SailSaveMode::Overwrite,
                options,
            )
            .await?;
        }
        Ok(())
    }

    /// Runs one Grust algorithm on a staged graph in the server and returns
    /// its rows as Arrow IPC streams. `configuration` is the map Grust's
    /// `grust.algorithms.*` procedures take, with positional arguments
    /// (`source`, `sources`) given by name.
    pub async fn run_algorithm(
        &self,
        graph: &str,
        algorithm: &str,
        configuration: &serde_json::Map<String, serde_json::Value>,
    ) -> Result<Vec<Vec<u8>>> {
        let mut options = HashMap::from([
            ("graph".to_string(), graph.to_string()),
            ("algorithm".to_string(), algorithm.to_string()),
        ]);
        for (key, value) in configuration {
            let text = match value {
                serde_json::Value::String(text) => text.clone(),
                other => other.to_string(),
            };
            options.insert(key.clone(), text);
        }
        self.read_format_arrow_ipc(SAIL_ALGORITHMS_FORMAT, options)
            .await
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn projection_sql_uses_the_grust_arrow_layout() {
        assert_eq!(
            sail_algorithm_nodes_sql(),
            "SELECT id AS node_id, label AS label FROM grust_nodes"
        );
        let sql = sail_algorithm_edges_sql(&["weight"]).unwrap();
        assert_eq!(
            sql,
            "SELECT id AS edge_id, src_id AS source, dst_id AS target, edge_type AS label, \
             CAST(GET_JSON_OBJECT(props, '$.weight') AS DOUBLE) AS weight FROM grust_edges"
        );
        assert!(sail_algorithm_edges_sql(&["w; DROP"]).is_err());
    }
}

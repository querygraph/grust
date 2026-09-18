//! Bulk loading through the engine's file `COPY`.
//!
//! One `MERGE` per node or edge costs the engine a full statement each,
//! measured at about 50 ms of CPU for a relationship `MERGE … SET` on a 4-vCPU
//! host, so a 200,000-edge slice took five hours. Registering the rows as an
//! Arrow table and running `COPY … FROM (MATCH …)` over it fixed the nodes
//! (a million rows a second) but not the edges: that probe is superlinear in
//! the engine, 4,100 edges a second at 500,000 and unfinished after two hours
//! at five million, which is why cit-Patents never loaded. The engine's own
//! `COPY … FROM 'file.csv'` takes the same rows, STRING keys and JSON props
//! included, at 1.3 million edges a second (five million in 3.9 s; 2.2 million
//! nodes a second), so every bulk write goes through a temporary CSV file.
//! The `lbug` crate has no equivalent of Python's `COPY … FROM $df`, and the
//! binder rejects `COPY … FROM <registered arrow table>`.
//!
//! `put_graph` keeps its upsert semantics: rows whose node id, or whose
//! `(from, to)` pair for a relationship table, already exists go through the
//! per-row `MERGE` path exactly as before; every other row is copied. Within
//! one load the last row for an id or pair wins, which is what a sequence of
//! `MERGE`s would leave behind. An empty target table skips the read-back of
//! existing keys, so a fresh load costs nothing beyond the copy.

use std::collections::{BTreeMap, HashSet};

use arrow::record_batch::RecordBatch;
use grust_core::prelude::*;

use super::{LadybugGraphStore, ladybug_error, props_to_string};

impl LadybugGraphStore {
    /// Write `nodes` into `table`, copying rows whose id is new and merging
    /// the rest. Returns how many rows were written.
    pub(super) fn bulk_write_nodes_locked(
        &self,
        conn: &lbug::Connection<'_>,
        table: &str,
        nodes: &[&Node],
    ) -> Result<usize> {
        let existing = if Self::count(conn, &format!("MATCH (n:{table}) RETURN count(n);"))? == 0 {
            HashSet::new()
        } else {
            self.existing_node_ids(conn, table)?
        };
        let mut fresh: BTreeMap<&str, &Node> = BTreeMap::new();
        for node in nodes {
            if existing.contains(node.id.as_str()) {
                self.write_node_locked(conn, node, table)?;
            } else {
                fresh.insert(node.id.as_str(), node);
            }
        }
        if fresh.is_empty() {
            return Ok(nodes.len());
        }
        let ids: Vec<&str> = fresh.keys().copied().collect();
        let props = fresh
            .values()
            .map(|node| props_to_string(&node.props))
            .collect::<Result<Vec<_>>>()?;
        let batch = string_batch(&[
            ("id", ids.clone()),
            ("props", props.iter().map(String::as_str).collect()),
        ])?;
        self.copy_from_csv(conn, table, &batch)?;
        self.bulk_write_node_index(conn, table, &fresh)?;
        Ok(nodes.len())
    }

    /// Write `edges` into `rel_table`, copying pairs that are new and merging
    /// the rest. Returns how many rows were written.
    pub(super) fn bulk_write_edges_locked(
        &self,
        conn: &lbug::Connection<'_>,
        rel_table: &str,
        from_table: &str,
        to_table: &str,
        edges: &[&Edge],
    ) -> Result<usize> {
        let existing = if Self::count(
            conn,
            &format!("MATCH ()-[r:{rel_table}]->() RETURN count(r);"),
        )? == 0
        {
            HashSet::new()
        } else {
            self.existing_edge_pairs(conn, rel_table, from_table, to_table)?
        };
        let mut fresh: BTreeMap<(&str, &str), &Edge> = BTreeMap::new();
        for edge in edges {
            let pair = (edge.from.as_str(), edge.to.as_str());
            if existing.contains(&(pair.0.to_string(), pair.1.to_string())) {
                self.write_edge_locked(conn, edge, rel_table, from_table, to_table)?;
            } else {
                fresh.insert(pair, edge);
            }
        }
        if fresh.is_empty() {
            return Ok(edges.len());
        }
        let ids = fresh
            .values()
            .map(|edge| checked_edge_key(edge))
            .collect::<Result<Vec<_>>>()?;
        let props = fresh
            .values()
            .map(|edge| props_to_string(&edge.props))
            .collect::<Result<Vec<_>>>()?;
        let batch = string_batch(&[
            ("from", fresh.keys().map(|(from, _)| *from).collect()),
            ("to", fresh.keys().map(|(_, to)| *to).collect()),
            ("id", ids.iter().map(String::as_str).collect()),
            ("props", props.iter().map(String::as_str).collect()),
        ])?;
        // Positional: FROM, TO, then the rel table's own columns.
        self.copy_from_csv(conn, rel_table, &batch)?;
        Ok(edges.len())
    }

    /// Writes `batch` to a temporary CSV and runs the engine's `COPY` over it,
    /// columns positional. The file lives only for the statement.
    fn copy_from_csv(
        &self,
        conn: &lbug::Connection<'_>,
        table: &str,
        batch: &RecordBatch,
    ) -> Result<()> {
        let io = |err: std::io::Error| {
            GrustError::Backend(format!("Ladybug bulk copy file error: {err}"))
        };
        let dir = tempfile::Builder::new()
            .prefix("grust-ladybug-copy-")
            .tempdir()
            .map_err(io)?;
        let path = dir.path().join("rows.csv");
        {
            let file = std::fs::File::create(&path).map_err(io)?;
            let mut writer = arrow::csv::WriterBuilder::new()
                .with_header(false)
                .build(file);
            writer.write(batch).map_err(|err| {
                GrustError::Serialization(format!("Ladybug bulk copy CSV error: {err}"))
            })?;
        }
        let path = path.display().to_string();
        if path.contains('\'') {
            return Err(GrustError::Backend(format!(
                "Ladybug bulk copy: temp path has a quote: {path}"
            )));
        }
        Self::exec(
            conn,
            &format!(
                "COPY {table} FROM '{path}' (HEADER=false, DELIM=',', QUOTE='\"', ESCAPE='\"');"
            ),
        )
    }

    /// One integer from a `RETURN count(…)` query.
    fn count(conn: &lbug::Connection<'_>, query: &str) -> Result<i64> {
        let mut rows = conn.query(query).map_err(ladybug_error)?;
        match rows.next().as_deref() {
            Some([lbug::Value::Int64(n), ..]) => Ok(*n),
            other => Err(GrustError::Serialization(format!(
                "Ladybug count returned {other:?}"
            ))),
        }
    }

    /// The metadata index gets one row per new node, copied the same way.
    fn bulk_write_node_index(
        &self,
        conn: &lbug::Connection<'_>,
        table: &str,
        fresh: &BTreeMap<&str, &Node>,
    ) -> Result<()> {
        let (node_index, _) = self.metadata_tables()?;
        let labels: Vec<&str> = fresh.values().map(|node| node.label.as_str()).collect();
        let batch = string_batch(&[
            ("id", fresh.keys().copied().collect()),
            ("kind", vec!["node"; fresh.len()]),
            ("label", labels),
            ("table_name", vec![table; fresh.len()]),
        ])?;
        self.copy_from_csv(conn, node_index, &batch)
    }

    fn existing_node_ids(
        &self,
        conn: &lbug::Connection<'_>,
        table: &str,
    ) -> Result<HashSet<String>> {
        let rows = conn
            .query(&format!("MATCH (n:{table}) RETURN n.id;"))
            .map_err(ladybug_error)?;
        rows.map(|row| super::row_string(&row, 0, "node id"))
            .collect()
    }

    fn existing_edge_pairs(
        &self,
        conn: &lbug::Connection<'_>,
        rel_table: &str,
        from_table: &str,
        to_table: &str,
    ) -> Result<HashSet<(String, String)>> {
        let rows = conn
            .query(&format!(
                "MATCH (a:{from_table})-[r:{rel_table}]->(b:{to_table}) RETURN a.id, b.id;"
            ))
            .map_err(ladybug_error)?;
        rows.map(|row| {
            Ok((
                super::row_string(&row, 0, "edge")?,
                super::row_string(&row, 1, "edge")?,
            ))
        })
        .collect()
    }
}

/// A record batch of non-null UTF-8 columns.
fn string_batch(columns: &[(&str, Vec<&str>)]) -> Result<RecordBatch> {
    grust_arrow::v55::string_batch(columns)
        .map_err(|err| GrustError::Serialization(format!("Ladybug Arrow batch error: {err}")))
}

#[cfg(test)]
mod tests {
    use super::super::LadybugGraphStore;
    use grust_core::prelude::*;
    use serde_json::json;

    fn props(pairs: &[(&str, serde_json::Value)]) -> Props {
        pairs
            .iter()
            .map(|(k, v)| (k.to_string(), v.clone()))
            .collect()
    }

    /// Values that break naive CSV: commas, double quotes, newlines, a
    /// backslash, a quote-only string, an empty string, unicode.
    #[test]
    fn bulk_copy_round_trips_hostile_props_and_then_upserts() -> Result<()> {
        let rt = tokio::runtime::Runtime::new().unwrap();
        rt.block_on(async {
            let store = LadybugGraphStore::in_memory()?;
            let nasty = props(&[
                ("comma", json!("a,b")),
                ("quote", json!("say \"hi\"")),
                ("newline", json!("line1\nline2")),
                ("backslash", json!("c:\\path")),
                ("only_quote", json!("\"")),
                ("empty", json!("")),
                ("unicode", json!("naïve 日本 🚀")),
                ("nested", json!({"k": ["x,y", "\"z\""]})),
            ]);
            let nodes: Vec<Node> = (0..3)
                .map(|i| Node::new("Thing", format!("n{i}"), nasty.clone()))
                .collect();
            let edges = vec![
                Edge::new("REL", "n0", "n1", nasty.clone()),
                Edge::new("REL", "n1", "n2", props(&[("plain", json!(1))])),
            ];
            let report = store.put_graph(&Graph::new(nodes, edges)).await?;
            assert_eq!((report.nodes, report.edges), (3, 2));
            let got = store.get_node(&NodeId::new("n1")).await?.expect("n1");
            assert_eq!(got.props, nasty);
            let out = store
                .get_edges(EdgeQuery {
                    from: Some(NodeId::new("n0")),
                    ..Default::default()
                })
                .await?;
            assert_eq!(out.len(), 1);
            assert_eq!(out[0].props, nasty);

            // A second load of the same ids takes the merge path (the tables
            // are no longer empty) and must not duplicate anything.
            let again = Graph::new(
                vec![Node::new("Thing", "n1", props(&[("v", json!(2))]))],
                vec![Edge::new("REL", "n0", "n1", props(&[("v", json!(2))]))],
            );
            store.put_graph(&again).await?;
            let got = store.get_node(&NodeId::new("n1")).await?.expect("n1");
            assert_eq!(got.props, props(&[("v", json!(2))]));
            let out = store
                .get_edges(EdgeQuery {
                    from: Some(NodeId::new("n0")),
                    ..Default::default()
                })
                .await?;
            assert_eq!(out.len(), 1, "upsert must not add a parallel edge");
            assert_eq!(out[0].props, props(&[("v", json!(2))]));
            Ok(())
        })
    }
}

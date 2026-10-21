//! Import through ArcadeDB's own bulk endpoint (`/api/v1/batch`), one streamed
//! request, into a database this run creates. Post and Comment are subtypes of
//! Message and keep `kind`, so `(:Message)`, `(:Post)` and `{kind: ...}` all
//! match as in the reference model. Edges keep their multiplicity and `id`.
use std::collections::BTreeSet;
use std::fs;
use std::path::Path;
use std::time::Instant;

use grust_core::{Props, Value};
use grust_lsqb_runner::dataset;
use serde_json::{Map, json};

use super::{Settings, http::Connection, identifier, ok};

pub(super) struct Loaded {
    pub nodes: usize,
    pub edges: usize,
    pub import_ns: u128,
    pub view_ns: u128,
}

/// Vertex and edge types named by the projected CSV files (`Type.csv`,
/// `Source_relation_Target.csv`), the same names the dataset reader assigns.
fn schema(directory: &Path) -> Result<(Vec<String>, Vec<String>), &'static str> {
    let (mut vertices, mut edges) = (BTreeSet::new(), BTreeSet::new());
    for entry in fs::read_dir(directory).map_err(|_| "dataset directory unreadable")? {
        let path = entry.map_err(|_| "dataset directory unreadable")?.path();
        if path.extension().is_none_or(|extension| extension != "csv") {
            continue;
        }
        let stem = path
            .file_stem()
            .and_then(|stem| stem.to_str())
            .ok_or("dataset file name is not UTF-8")?;
        match stem.split('_').collect::<Vec<_>>().as_slice() {
            [vertex] => {
                vertices.insert(identifier(vertex)?.to_string());
            }
            [_, relation, _] => {
                edges.insert(identifier(&upper_snake(relation))?.to_string());
            }
            _ => return Err("unexpected projected dataset file name"),
        }
    }
    if vertices.is_empty() || edges.is_empty() {
        return Err("projected dataset has no vertex or edge files");
    }
    Ok((vertices.into_iter().collect(), edges.into_iter().collect()))
}

fn upper_snake(value: &str) -> String {
    let mut output = String::new();
    for (index, ch) in value.chars().enumerate() {
        if ch.is_ascii_uppercase() && index != 0 {
            output.push('_');
        }
        output.push(ch.to_ascii_uppercase());
    }
    output
}

/// Message rows carry their concrete subtype in `kind`.
fn vertex_type<'a>(label: &'a str, props: &'a Props) -> &'a str {
    match props.get("kind") {
        Some(Value::String(kind))
            if label == "Message" && ["Post", "Comment"].contains(&kind.as_str()) =>
        {
            kind
        }
        _ => label,
    }
}

fn properties(props: &Props, row: &mut Map<String, serde_json::Value>) -> Result<(), &'static str> {
    for (key, value) in props {
        let value = match value {
            Value::String(value) => json!(value),
            Value::Int(value) => json!(value),
            Value::Bool(value) => json!(value),
            _ => return Err("unexpected property type in projected dataset"),
        };
        row.insert(key.clone(), value);
    }
    Ok(())
}

fn ndjson(chunk: &grust_core::Graph) -> Result<Vec<u8>, &'static str> {
    let mut output = Vec::new();
    for node in &chunk.nodes {
        let mut row = Map::new();
        row.insert("@type".into(), json!("vertex"));
        row.insert(
            "@class".into(),
            json!(identifier(vertex_type(node.label.as_str(), &node.props))?),
        );
        row.insert("@id".into(), json!(node.id.as_str()));
        properties(&node.props, &mut row)?;
        serde_json::to_writer(&mut output, &row).map_err(|_| "serialize vertex failed")?;
        output.push(b'\n');
    }
    for edge in &chunk.edges {
        let row = json!({"@type": "edge", "@class": identifier(edge.label.as_str())?,
            "@from": edge.from.as_str(), "@to": edge.to.as_str(),
            "id": edge.id.as_ref().ok_or("projected edge id missing")?.as_str()});
        serde_json::to_writer(&mut output, &row).map_err(|_| "serialize edge failed")?;
        output.push(b'\n');
    }
    Ok(output)
}

fn command(
    connection: &mut Connection,
    settings: &Settings,
    sql: &str,
) -> Result<(), &'static str> {
    let response = connection.json(
        &format!("/api/v1/command/{}", settings.database),
        None,
        &json!({"language": "sql", "command": sql}),
    )?;
    ok(response, "ArcadeDB schema command failed").map(|_| ())
}

pub(super) fn load(
    connection: &mut Connection,
    settings: &Settings,
    directory: &Path,
    expected_records: usize,
    mut progress: impl FnMut(usize, usize) -> Result<(), &'static str>,
) -> Result<Loaded, &'static str> {
    if std::env::var("ARCADEDB_BENCHMARK_DISPOSABLE").as_deref() != Ok("1") {
        return Err("import requires explicit ARCADEDB_BENCHMARK_DISPOSABLE=1");
    }
    let database = &settings.database;
    let exists = ok(
        connection.request("GET", &format!("/api/v1/exists/{database}"), None, b"")?,
        "ArcadeDB database existence check failed",
    )?;
    if exists.get("result") != Some(&json!(false)) {
        return Err("refusing to import into an existing ArcadeDB database");
    }
    let started = Instant::now();
    ok(
        connection.json(
            "/api/v1/server",
            None,
            &json!({"command": format!("create database {database}")}),
        )?,
        "ArcadeDB database creation failed",
    )?;
    let (vertices, edges) = schema(directory)?;
    let subtypes = ["Post", "Comment"];
    if vertices
        .iter()
        .any(|vertex| subtypes.contains(&vertex.as_str()))
    {
        command(connection, settings, "CREATE VERTEX TYPE Message")?;
    }
    for vertex in &vertices {
        if subtypes.contains(&vertex.as_str()) {
            command(
                connection,
                settings,
                &format!("CREATE VERTEX TYPE {vertex} EXTENDS Message"),
            )?;
        } else {
            command(
                connection,
                settings,
                &format!("CREATE VERTEX TYPE {vertex}"),
            )?;
        }
    }
    for edge in &edges {
        command(connection, settings, &format!("CREATE EDGE TYPE {edge}"))?;
    }
    let chunks = dataset::projected_dataset_chunks(directory, 10_000)
        .map_err(|_| "projected dataset chunks unavailable")?;
    let (mut sent_nodes, mut sent_edges) = (0, 0);
    let body = chunks.map(|chunk| {
        let chunk = chunk.map_err(|_| "projected dataset decoding failed")?;
        let bytes = ndjson(&chunk)?;
        sent_nodes += chunk.nodes.len();
        sent_edges += chunk.edges.len();
        progress(chunk.nodes.len(), chunk.edges.len())?;
        Ok(bytes)
    });
    let response = connection.stream(
        &format!("/api/v1/batch/{database}?expectedRecords={expected_records}"),
        "application/x-ndjson",
        body,
    )?;
    let summary = ok(response, "ArcadeDB bulk import failed")?;
    let created = |key: &str| summary.get(key).and_then(serde_json::Value::as_u64);
    let (nodes, edges_created) = (
        created("verticesCreated").ok_or("ArcadeDB import summary invalid")? as usize,
        created("edgesCreated").ok_or("ArcadeDB import summary invalid")? as usize,
    );
    if (nodes, edges_created) != (sent_nodes, sent_edges) {
        return Err("ArcadeDB import counts differ from the records sent");
    }
    let import_ns = started.elapsed().as_nanos();
    // The Graph Analytical View is ArcadeDB's read-optimised adjacency for
    // graph traversals; it is built once after import and disclosed as setup.
    let started = Instant::now();
    command(
        connection,
        settings,
        &format!(
            "CREATE GRAPH ANALYTICAL VIEW {database} VERTEX TYPES ({}) EDGE TYPES ({})",
            vertices.join(", "),
            edges.join(", ")
        ),
    )?;
    command(
        connection,
        settings,
        &format!("REBUILD GRAPH ANALYTICAL VIEW {database}"),
    )?;
    Ok(Loaded {
        nodes,
        edges: edges_created,
        import_ns,
        view_ns: started.elapsed().as_nanos(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use grust_core::{Edge, EdgeId, Graph, Node};

    #[test]
    fn schema_follows_the_projected_file_names() {
        let directory = tempfile::tempdir().unwrap();
        for name in [
            "Person.csv",
            "Comment.csv",
            "Post.csv",
            "Person_knows_Person.csv",
            "Comment_replyOf_Post.csv",
            "notes.txt",
        ] {
            fs::write(directory.path().join(name), "x\n").unwrap();
        }
        let (vertices, edges) = schema(directory.path()).unwrap();
        assert_eq!(vertices, ["Comment", "Person", "Post"]);
        assert_eq!(edges, ["KNOWS", "REPLY_OF"]);
        fs::write(directory.path().join("a_b.csv"), "x\n").unwrap();
        assert!(schema(directory.path()).is_err());
    }

    #[test]
    fn messages_become_their_subtype_and_keep_kind() {
        let post = Node::new(
            "Message",
            "Post:7",
            Props::from([
                ("kind".into(), Value::from("Post")),
                ("source_id".into(), Value::Int(7)),
            ]),
        );
        let person = Node::new("Person", "Person:1", Props::new());
        let edge = Edge::new("HAS_CREATOR", "Post:7", "Person:1", Props::new())
            .with_id(EdgeId::new("Post_hasCreator_Person:1"));
        let bytes = ndjson(&Graph::new(vec![post, person], vec![edge])).unwrap();
        let rows: Vec<serde_json::Value> = bytes
            .split(|byte| *byte == b'\n')
            .filter(|line| !line.is_empty())
            .map(|line| serde_json::from_slice(line).unwrap())
            .collect();
        assert_eq!(rows[0]["@class"], "Post");
        assert_eq!(rows[0]["@id"], "Post:7");
        assert_eq!(rows[0]["kind"], "Post");
        assert_eq!(rows[0]["id"], "Post:7");
        assert_eq!(rows[1]["@class"], "Person");
        assert_eq!(
            rows[2],
            json!({"@type": "edge", "@class": "HAS_CREATOR", "@from": "Post:7",
            "@to": "Person:1", "id": "Post_hasCreator_Person:1"})
        );
    }

    #[test]
    fn only_projected_scalar_properties_are_accepted() {
        let mut row = Map::new();
        assert!(
            properties(
                &Props::from([("id".into(), Value::from("Person:1"))]),
                &mut row
            )
            .is_ok()
        );
        assert!(
            properties(
                &Props::from([("unsupported".into(), Value::Null)]),
                &mut row
            )
            .is_err()
        );
    }
}

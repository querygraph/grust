use super::*;

async fn store() -> PostgresGraphStore {
    PostgresGraphStore::connect(PostgresGraphConfig {
        connection_string: std::env::var("GRUST_PG_URL").expect("set GRUST_PG_URL"),
        ..PostgresGraphConfig::default()
    })
    .await
    .expect("connect disposable PostgreSQL")
}

#[tokio::test]
#[ignore = "requires PostgreSQL (GRUST_PG_URL)"]
async fn streamed_reads_preserve_values_and_recover_after_late_errors() {
    let store = store().await;
    let props = Props::from([
        ("payload".into(), Value::String("雪'\\\n".repeat(256))),
        ("empty".into(), Value::Null),
        (
            "items".into(),
            Value::StringArray(vec!["x".into(), "é".into()]),
        ),
    ]);
    let encoded = sql_str(&serde_json::to_string(&props).unwrap());
    let nodes = store
        .query_nodes(&format!(
            "SELECT i::text AS id, 'N'::text AS label, {encoded}::text AS props \
         FROM generate_series(1, 4096) AS i ORDER BY i"
        ))
        .await
        .unwrap();
    assert_eq!(nodes.len(), 4096);
    for (slot, node) in nodes.iter().enumerate() {
        assert_eq!(node.id.as_str(), (slot + 1).to_string());
        assert_eq!(node.label.as_str(), "N");
        assert_eq!(node.props, props);
    }
    let edges = store
        .query_edges(&format!(
            "SELECT i::text AS id, 'a'::text AS from_id, 'b'::text AS to_id, \
         'T'::text AS label, {encoded}::text AS props \
         FROM generate_series(1, 4096) AS i ORDER BY i"
        ))
        .await
        .unwrap();
    assert_eq!(edges.len(), 4096);
    for (slot, edge) in edges.iter().enumerate() {
        assert_eq!(edge.id.as_ref().unwrap().as_str(), (slot + 1).to_string());
        assert_eq!(edge.from.as_str(), "a");
        assert_eq!(edge.to.as_str(), "b");
        assert_eq!(edge.label.as_str(), "T");
        assert_eq!(edge.props, props);
    }
    // A server error after a valid prefix must fail the whole read.
    let error = store
        .query_nodes(
            "SELECT (1 / (4096 - i))::text AS id, 'N'::text AS label, '{}'::text AS props \
         FROM generate_series(1, 4096) AS i",
        )
        .await
        .unwrap_err();
    assert!(matches!(error, GrustError::Backend(_)));
    let error = store
        .query_edges(
            "SELECT (1 / (4096 - i))::text AS id, 'a'::text AS from_id, 'b'::text AS to_id, \
         'T'::text AS label, '{}'::text AS props FROM generate_series(1, 4096) AS i",
        )
        .await
        .unwrap_err();
    assert!(matches!(error, GrustError::Backend(_)));
    // Early decoder return drops a stream with unread messages. Subsequent
    // queries must work; no successful prefix may escape as a complete read.
    for edge in [false, true] {
        let endpoints = if edge {
            "'a'::text AS from_id, 'b'::text AS to_id,"
        } else {
            ""
        };
        let sql = format!(
            "SELECT i::text AS id, {endpoints} 'N'::text AS label, \
             CASE WHEN i = 2048 THEN '{{' ELSE '{{}}' END::text AS props \
             FROM generate_series(1, 4096) AS i"
        );
        let error = if edge {
            store.query_edges(&sql).await.unwrap_err()
        } else {
            store.query_nodes(&sql).await.unwrap_err()
        };
        assert!(matches!(error, GrustError::Serialization(_)));
        let read = store
            .query_nodes("SELECT 'ok'::text AS id, 'N'::text AS label, '{}'::text AS props")
            .await
            .unwrap();
        assert_eq!(read[0].id.as_str(), "ok");
    }
    assert!(
        store
            .query_nodes(
                "SELECT ''::text AS id, ''::text AS label, '{}'::text AS props WHERE false"
            )
            .await
            .unwrap()
            .is_empty()
    );
    assert!(store.query_edges("SELECT NULL::text AS id, ''::text AS from_id, ''::text AS to_id, ''::text AS label, '{}'::text AS props WHERE false").await.unwrap().is_empty());
}

/// Opt-in setup diagnostic. Run each test in a fresh process with the same
/// binary. The buffered branch is the pre-change implementation. This is not
/// a query-performance cohort; an unfiltered --ignored run is not a valid
/// memory comparison because other tests share the process.
#[tokio::test]
#[ignore = "allocation diagnostic; requires GRUST_PG_URL; run alone in a fresh process"]
async fn postgres_read_allocation_diagnostic_buffered() {
    read_allocation_diagnostic("buffered").await;
}

#[tokio::test]
#[ignore = "allocation diagnostic; requires GRUST_PG_URL; run alone in a fresh process"]
async fn postgres_read_allocation_diagnostic_streamed() {
    read_allocation_diagnostic("streamed").await;
}

async fn read_allocation_diagnostic(mode: &str) {
    let store = store().await;
    let props = Props::from([("payload".into(), Value::String("x".repeat(1024)))]);
    let encoded = sql_str(&serde_json::to_string(&props).unwrap());
    let sql = format!(
        "SELECT i::text AS id, 'a'::text AS from_id, 'b'::text AS to_id, \
         'T'::text AS label, {encoded}::text AS props FROM generate_series(1, 100000) AS i"
    );
    let cpu_ticks = || {
        let stat = std::fs::read_to_string("/proc/self/stat").unwrap();
        let fields: Vec<_> = stat
            .rsplit_once(')')
            .unwrap()
            .1
            .split_whitespace()
            .collect();
        fields[11].parse::<u64>().unwrap() + fields[12].parse::<u64>().unwrap()
    };
    let load_start = std::fs::read_to_string("/proc/loadavg").unwrap();
    let cpu_start = cpu_ticks();
    let started = std::time::Instant::now();
    let edges: Vec<Edge> = if mode == "buffered" {
        let rows = store.client.query(&sql, &[]).await.unwrap();
        rows.into_iter()
            .map(prechange_row_to_edge)
            .collect::<Result<_>>()
            .unwrap()
    } else {
        store.query_edges(&sql).await.unwrap()
    };
    let wall_ms = started.elapsed().as_secs_f64() * 1000.0;
    let cpu = cpu_ticks() - cpu_start;
    let status = std::fs::read_to_string("/proc/self/status").unwrap();
    let peak_rss_kb = status
        .lines()
        .find(|line| line.starts_with("VmHWM:"))
        .unwrap();
    let load_end = std::fs::read_to_string("/proc/loadavg").unwrap();
    assert_eq!(edges.len(), 100000);
    for (slot, edge) in edges.iter().enumerate() {
        assert_eq!(edge.id.as_ref().unwrap().as_str(), (slot + 1).to_string());
        assert_eq!(edge.from.as_str(), "a");
        assert_eq!(edge.to.as_str(), "b");
        assert_eq!(edge.label.as_str(), "T");
        assert_eq!(edge.props, props);
    }
    println!(
        "{}",
        serde_json::json!({
            "mode": mode, "edges": edges.len(), "property_payload_bytes": 1024,
            "wall_ms_upper_bound": wall_ms, "client_cpu_ticks": cpu,
            "client_peak_rss": peak_rss_kb, "host_loadavg_start": load_start,
            "host_loadavg_end": load_end,
        "profile": if cfg!(debug_assertions) { "debug" } else { "release" },
        "boundary": "read and decode; synthetic diagnostic; server CPU not measured"
        })
    );
}

// Retained solely for the opt-in before/after diagnostic: both collection
// and owned text decoding match the reviewed pre-change implementation.
fn prechange_row_to_edge(row: tokio_postgres::Row) -> Result<Edge> {
    let id: Option<String> = row.get("id");
    let from_id: String = row.get("from_id");
    let to_id: String = row.get("to_id");
    let label: String = row.get("label");
    let props_json: String = row.get("props");
    let props: Props = serde_json::from_str(&props_json)
        .map_err(|err| GrustError::Serialization(format!("edge props JSON parse failed: {err}")))?;
    let mut edge = Edge::new(label, from_id, to_id, props);
    edge.id = id.map(EdgeId::new);
    Ok(edge)
}

use super::*;

#[tokio::test]
async fn cached_reader_observes_writes_through_another_connection() {
    let directory = tempfile::tempdir().unwrap();
    let config = LanceDbConfig {
        uri: directory.path().display().to_string(),
        ..Default::default()
    };
    let reader = LanceDbGraphStore::connect(config.clone()).await.unwrap();
    reader.bootstrap().await.unwrap();
    let id = NodeId::new("shared");
    reader
        .put_node(&Node::new("N", "shared", [("value".into(), Value::Int(1))]))
        .await
        .unwrap();
    assert_eq!(
        reader
            .get_node(&id)
            .await
            .unwrap()
            .unwrap()
            .props
            .get("value"),
        Some(&Value::Int(1))
    );
    let writer = LanceDbGraphStore::connect(config).await.unwrap();
    writer
        .put_node(&Node::new("N", "shared", [("value".into(), Value::Int(2))]))
        .await
        .unwrap();
    assert_eq!(
        reader
            .get_node(&id)
            .await
            .unwrap()
            .unwrap()
            .props
            .get("value"),
        Some(&Value::Int(2))
    );
}

#[tokio::test]
async fn recreation_and_first_lookup_share_one_gate() {
    let directory = tempfile::tempdir().unwrap();
    let store = LanceDbGraphStore::connect(LanceDbConfig {
        uri: directory.path().display().to_string(),
        ..Default::default()
    })
    .await
    .unwrap();
    store.bootstrap().await.unwrap();
    store
        .put_node(&Node::new("N", "old", Props::new()))
        .await
        .unwrap();
    let gate = store.handles.tables.lock().await;
    let mut clear = Box::pin(store.clear());
    let mut lookup = Box::pin(store.open_nodes());
    assert!(futures::poll!(&mut clear).is_pending());
    assert!(futures::poll!(&mut lookup).is_pending());
    drop(gate);
    let (cleared, table) = futures::join!(clear, lookup);
    cleared.unwrap();
    // Even when an earlier lookup may retain a handle, the resident cache after
    // recreation must describe the new tables. No old lookup can republish it.
    drop(table.unwrap());
    assert_eq!(
        store
            .open_nodes()
            .await
            .unwrap()
            .count_rows(None)
            .await
            .unwrap(),
        0
    );
    assert!(store.get_node(&NodeId::new("old")).await.unwrap().is_none());
}

//! Registry cleanup tests; these do not establish an object-store effect barrier.

use datafusion::arrow::datatypes::Schema;
use futures::TryStreamExt;
use object_store::{ObjectStore, ObjectStoreExt};
use tokio::sync::oneshot;

use super::*;

#[path = "remote_checkpoint_test_store.rs"]
mod support;
use support::{ControlledStore, DeleteFailure};

type TestResult = std::result::Result<(), Box<dyn std::error::Error>>;

fn descriptor(relation_id: &str) -> Result<RemoteCheckpointDescriptor> {
    let schema = Arc::new(Schema::empty());
    Ok(RemoteCheckpointDescriptor {
        relation_id: relation_id.into(),
        object_store_url: ObjectStoreUrl::parse("memory://")?,
        prefix: Path::from("checkpoint/session/relation"),
        logical_schema: schema.clone(),
        storage_schema: schema,
        output_partitioning: Partitioning::UnknownPartitioning(1),
        output_ordering: None,
        partitions: vec![],
    })
}

fn runtime(store: Arc<ControlledStore>) -> Result<RuntimeEnv> {
    let runtime = RuntimeEnv::default();
    runtime.register_object_store(ObjectStoreUrl::parse("memory://")?.as_ref(), store);
    Ok(runtime)
}

fn new_registry(session: &str) -> RemoteCheckpointRegistry {
    RemoteCheckpointRegistry::new(Some("memory:///checkpoint".into()), session.into())
}

fn retained(
    registry: &RemoteCheckpointRegistry,
    relation_id: &str,
) -> std::result::Result<Option<Arc<RemoteCheckpointDescriptor>>, Box<dyn std::error::Error>> {
    // Inspect private retained metadata, separately from the public closed view.
    let relations = registry
        .relations
        .try_read()
        .map_err(|error| error.to_string())?;
    Ok(relations.get(relation_id).cloned())
}

async fn paths(store: &ControlledStore) -> object_store::Result<Vec<Path>> {
    let mut paths = store
        .list(None)
        .map_ok(|metadata| metadata.location)
        .try_collect::<Vec<_>>()
        .await?;
    paths.sort();
    Ok(paths)
}

fn assert_closed(registry: &RemoteCheckpointRegistry, runtime: &RuntimeEnv) -> TestResult {
    assert!(registry.get("relation")?.is_none());
    assert!(matches!(
        registry.insert(descriptor("late")?),
        Err(DataFusionError::Plan(message)) if message == "checkpoint session is stopping"
    ));
    assert!(matches!(
        registry.resolve_relation(runtime, "late"),
        Err(DataFusionError::Plan(message)) if message == "checkpoint session is stopping"
    ));
    Ok(())
}

#[tokio::test]
async fn partial_delete_failure_retains_descriptor_for_explicit_retry() -> TestResult {
    let first = Path::from("checkpoint/session/relation/a.parquet");
    let second = Path::from("checkpoint/session/relation/b.parquet");
    let outside = Path::from("checkpoint/other/relation/keep.parquet");
    let store = Arc::new(ControlledStore::fail_once(second.clone()));
    for path in [&first, &second, &outside] {
        store.put(path, "checkpoint".into()).await?;
    }
    let runtime = runtime(store.clone())?;
    let registry = new_registry("session");
    registry.insert(descriptor("relation")?)?;
    let original = registry.get("relation")?.ok_or("descriptor missing")?;

    let error = registry
        .cleanup_session(&runtime)
        .await
        .err()
        .ok_or("partial deletion unexpectedly succeeded")?;
    let DataFusionError::ObjectStore(error) = error else {
        return Err("storage error type was replaced".into());
    };
    let object_store::Error::PermissionDenied { path, source } = error.as_ref() else {
        return Err("original deletion error was replaced".into());
    };
    assert_eq!(path, &second.to_string());
    assert!(source.downcast_ref::<DeleteFailure>().is_some());
    assert_eq!(paths(&store).await?, vec![outside.clone(), second.clone()]);
    // This assertion fails on the unchanged production implementation, which
    // clears the map even though the second object could not be deleted.
    let saved = retained(&registry, "relation")?.ok_or("cleanup discarded recovery metadata")?;
    assert!(Arc::ptr_eq(&original, &saved));
    assert_closed(&registry, &runtime)?;

    registry.cleanup_session(&runtime).await?;
    assert_eq!(paths(&store).await?, vec![outside]);
    assert!(retained(&registry, "relation")?.is_none());
    assert_closed(&registry, &runtime)?;
    Ok(())
}

#[tokio::test]
async fn paused_deletion_seals_admission_without_holding_the_registry_lock() -> TestResult {
    let (entered, observed) = oneshot::channel();
    let (release, pending) = oneshot::channel();
    let store = Arc::new(ControlledStore::paused(entered, pending));
    let object = Path::from("checkpoint/session/relation/data.parquet");
    store.put(&object, "checkpoint".into()).await?;
    let runtime = runtime(store.clone())?;
    let registry = new_registry("session");
    registry.insert(descriptor("relation")?)?;
    let original = registry.get("relation")?.ok_or("descriptor missing")?;

    let cleanup = registry.cleanup_session(&runtime);
    tokio::pin!(cleanup);
    assert!(futures::poll!(cleanup.as_mut()).is_pending());
    observed.await?;
    // try_write makes a held lock fail immediately rather than deadlocking this
    // current-thread runtime. This checks the paused I/O phase, not every
    // scheduling interleaving of concurrent insert and seal.
    {
        let relations = registry
            .relations
            .try_write()
            .map_err(|error| error.to_string())?;
        let saved = relations
            .get("relation")
            .ok_or("descriptor discarded before deletion")?;
        assert!(Arc::ptr_eq(&original, saved));
    }
    assert_closed(&registry, &runtime)?;
    assert_eq!(paths(&store).await?, vec![object]);
    release
        .send(())
        .map_err(|_| "deletion waiter was dropped")?;
    cleanup.await?;
    assert!(paths(&store).await?.is_empty());
    assert!(retained(&registry, "relation")?.is_none());
    assert_closed(&registry, &runtime)?;
    Ok(())
}

#[tokio::test]
async fn canceled_cleanup_retains_closed_metadata_for_explicit_retry() -> TestResult {
    let (entered, observed) = oneshot::channel();
    let (release, pending) = oneshot::channel();
    let store = Arc::new(ControlledStore::paused(entered, pending));
    let object = Path::from("checkpoint/session/relation/data.parquet");
    store.put(&object, "checkpoint".into()).await?;
    let runtime = runtime(store.clone())?;
    let registry = new_registry("session");
    registry.insert(descriptor("relation")?)?;
    let original = registry.get("relation")?.ok_or("descriptor missing")?;

    let mut cleanup = Box::pin(registry.cleanup_session(&runtime));
    assert!(futures::poll!(cleanup.as_mut()).is_pending());
    observed.await?;
    drop(cleanup);
    // Dropping this fake store's pending request drops its gate receiver. This
    // does not assert that a real provider's mutation stops with its awaiter.
    assert!(release.send(()).is_err());
    let saved = retained(&registry, "relation")?.ok_or("cancellation discarded metadata")?;
    assert!(Arc::ptr_eq(&original, &saved));
    assert_closed(&registry, &runtime)?;
    assert_eq!(paths(&store).await?, vec![object]);

    registry.cleanup_session(&runtime).await?;
    assert!(paths(&store).await?.is_empty());
    assert!(retained(&registry, "relation")?.is_none());
    assert_closed(&registry, &runtime)?;
    Ok(())
}

#[tokio::test]
async fn successful_cleanup_is_session_scoped_and_remains_closed() -> TestResult {
    let store = Arc::new(ControlledStore::default());
    let removed = Path::from("checkpoint/session/relation/data.parquet");
    let kept = Path::from("checkpoint/sibling/relation/data.parquet");
    for path in [&removed, &kept] {
        store.put(path, "checkpoint".into()).await?;
    }
    let runtime = runtime(store.clone())?;
    let registry = new_registry("session");
    let sibling = new_registry("sibling");
    registry.insert(descriptor("relation")?)?;
    sibling.insert(descriptor("relation")?)?;
    let original = sibling
        .get("relation")?
        .ok_or("sibling descriptor missing")?;

    registry.cleanup_session(&runtime).await?;
    assert_eq!(paths(&store).await?, vec![kept]);
    assert!(retained(&registry, "relation")?.is_none());
    assert_closed(&registry, &runtime)?;
    assert!(Arc::ptr_eq(
        &original,
        &sibling
            .get("relation")?
            .ok_or("sibling descriptor discarded")?,
    ));
    sibling.insert(descriptor("new")?)?;
    assert!(sibling.resolve_relation(&runtime, "new").is_ok());
    // Repeating successful cleanup does not reopen the closed registry.
    registry.cleanup_session(&runtime).await?;
    assert_closed(&registry, &runtime)?;
    Ok(())
}

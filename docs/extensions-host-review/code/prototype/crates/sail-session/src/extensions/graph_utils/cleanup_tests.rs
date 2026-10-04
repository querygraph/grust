use std::sync::Arc;
use std::sync::atomic::{AtomicUsize, Ordering};

use async_trait::async_trait;
use datafusion::execution::runtime_env::RuntimeEnv;
use datafusion_common::{Result, plan_datafusion_err};
use futures::TryStreamExt;
use futures::stream::BoxStream;
use object_store::memory::InMemory;
use object_store::path::Path;
use object_store::{
    CopyOptions, GetOptions, GetResult, ListResult, MultipartUpload, ObjectMeta, ObjectStore,
    PutMultipartOptions, PutOptions, PutPayload, PutResult,
};

use super::proto::request::Verb;
use super::proto::{Mkdir, Request};
use super::storage::GraphRuns;

#[derive(Debug)]
struct FailLists {
    inner: InMemory,
    failures_remaining: AtomicUsize,
    list_calls: AtomicUsize,
}
impl std::fmt::Display for FailLists {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("FailLists")
    }
}
#[async_trait]
impl ObjectStore for FailLists {
    async fn put_opts(
        &self,
        path: &Path,
        payload: PutPayload,
        opts: PutOptions,
    ) -> object_store::Result<PutResult> {
        self.inner.put_opts(path, payload, opts).await
    }
    async fn put_multipart_opts(
        &self,
        path: &Path,
        opts: PutMultipartOptions,
    ) -> object_store::Result<Box<dyn MultipartUpload>> {
        self.inner.put_multipart_opts(path, opts).await
    }
    async fn get_opts(&self, path: &Path, opts: GetOptions) -> object_store::Result<GetResult> {
        self.inner.get_opts(path, opts).await
    }
    fn delete_stream(
        &self,
        locations: BoxStream<'static, object_store::Result<Path>>,
    ) -> BoxStream<'static, object_store::Result<Path>> {
        self.inner.delete_stream(locations)
    }
    fn list(&self, prefix: Option<&Path>) -> BoxStream<'static, object_store::Result<ObjectMeta>> {
        self.list_calls.fetch_add(1, Ordering::SeqCst);
        if self
            .failures_remaining
            .fetch_update(Ordering::SeqCst, Ordering::SeqCst, |remaining| {
                remaining.checked_sub(1)
            })
            .is_ok()
        {
            Box::pin(futures::stream::once(async {
                Err(object_store::Error::Generic {
                    store: "FailLists",
                    source: std::io::Error::other("injected list failure").into(),
                })
            }))
        } else {
            self.inner.list(prefix)
        }
    }
    async fn list_with_delimiter(&self, prefix: Option<&Path>) -> object_store::Result<ListResult> {
        self.inner.list_with_delimiter(prefix).await
    }
    async fn copy_opts(
        &self,
        from: &Path,
        to: &Path,
        opts: CopyOptions,
    ) -> object_store::Result<()> {
        self.inner.copy_opts(from, to, opts).await
    }
}

async fn fixture() -> Result<(GraphRuns, Arc<FailLists>)> {
    let runtime = RuntimeEnv::default();
    let store = Arc::new(FailLists {
        inner: InMemory::new(),
        failures_remaining: AtomicUsize::new(0),
        list_calls: AtomicUsize::new(0),
    });
    runtime.register_object_store(
        &url::Url::parse("memory:///").map_err(|e| plan_datafusion_err!("{e}"))?,
        store.clone(),
    );
    let runs = GraphRuns::new(&runtime, "memory:///graphs")?;
    for _ in 0..3 {
        runs.execute(Request {
            verb: Some(Verb::Mkdir(Mkdir {
                root: String::new(),
                request_id: uuid::Uuid::new_v4().to_string(),
            })),
        })
        .await?;
    }
    Ok((runs, store))
}

#[tokio::test]
async fn production_cleanup_retries_a_transient_store_failure_and_attempts_every_run() -> Result<()>
{
    let (runs, store) = fixture().await?;
    store.failures_remaining.store(1, Ordering::SeqCst);
    // Exercise exactly the method called by session teardown: no manual retry.
    runs.cleanup().await?;
    // First pass attempts all three runs despite its first failure. A second
    // pass revisits every run, including those already cleaned successfully.
    assert_eq!(store.list_calls.load(Ordering::SeqCst), 6);
    assert!(store.inner.list(None).try_next().await?.is_none());
    Ok(())
}

#[tokio::test]
async fn production_cleanup_stops_after_bounded_attempts_and_preserves_failure() -> Result<()> {
    let (runs, store) = fixture().await?;
    store.failures_remaining.store(100, Ordering::SeqCst);
    let error = runs
        .cleanup()
        .await
        .err()
        .ok_or_else(|| plan_datafusion_err!("cleanup unexpectedly succeeded"))?;
    assert!(error.to_string().contains("exhausted 3 attempts"));
    assert!(error.to_string().contains("injected list failure"));
    assert_eq!(store.list_calls.load(Ordering::SeqCst), 9);
    assert_eq!(
        store.inner.list(None).try_collect::<Vec<_>>().await?.len(),
        3
    );
    Ok(())
}

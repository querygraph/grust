//! Minimal forwarding fault store, following the private VacuumStore test pattern.

use std::fmt;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};

use futures::stream::BoxStream;
use futures::{StreamExt, TryStreamExt, stream};
use object_store::memory::InMemory;
use object_store::path::Path;
use object_store::{
    CopyOptions, GetOptions, GetResult, ListResult, MultipartUpload, ObjectMeta, ObjectStore,
    ObjectStoreExt, PutMultipartOptions, PutOptions, PutPayload, PutResult,
};
use tokio::sync::oneshot;

#[derive(Debug)]
pub(super) struct DeleteFailure;

impl fmt::Display for DeleteFailure {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "injected checkpoint deletion failure")
    }
}

impl std::error::Error for DeleteFailure {}

#[derive(Debug, Default)]
pub(super) struct ControlledStore {
    inner: Arc<InMemory>,
    fail_path: Option<Path>,
    fail_once: Arc<AtomicBool>,
    entered: Mutex<Option<oneshot::Sender<()>>>,
    release: Mutex<Option<oneshot::Receiver<()>>>,
}

impl ControlledStore {
    pub(super) fn fail_once(path: Path) -> Self {
        Self {
            fail_path: Some(path),
            fail_once: Arc::new(AtomicBool::new(true)),
            ..Default::default()
        }
    }

    pub(super) fn paused(entered: oneshot::Sender<()>, release: oneshot::Receiver<()>) -> Self {
        Self {
            entered: Mutex::new(Some(entered)),
            release: Mutex::new(Some(release)),
            ..Default::default()
        }
    }
}

impl fmt::Display for ControlledStore {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "ControlledCheckpointStore")
    }
}

#[async_trait::async_trait]
impl ObjectStore for ControlledStore {
    async fn put_opts(
        &self,
        location: &Path,
        payload: PutPayload,
        options: PutOptions,
    ) -> object_store::Result<PutResult> {
        self.inner.put_opts(location, payload, options).await
    }

    async fn put_multipart_opts(
        &self,
        location: &Path,
        options: PutMultipartOptions,
    ) -> object_store::Result<Box<dyn MultipartUpload>> {
        self.inner.put_multipart_opts(location, options).await
    }

    async fn get_opts(
        &self,
        location: &Path,
        options: GetOptions,
    ) -> object_store::Result<GetResult> {
        self.inner.get_opts(location, options).await
    }

    fn delete_stream(
        &self,
        locations: BoxStream<'static, object_store::Result<Path>>,
    ) -> BoxStream<'static, object_store::Result<Path>> {
        let inner = self.inner.clone();
        let fail_path = self.fail_path.clone();
        let fail_once = self.fail_once.clone();
        let entered = self
            .entered
            .lock()
            .unwrap_or_else(|error| error.into_inner())
            .take();
        let release = self
            .release
            .lock()
            .unwrap_or_else(|error| error.into_inner())
            .take();
        stream::once(async move {
            let mut paths = locations.try_collect::<Vec<_>>().await?;
            paths.sort();
            if let Some(entered) = entered {
                let _ = entered.send(());
            }
            if let Some(release) = release {
                release
                    .await
                    .map_err(|error| object_store::Error::Generic {
                        store: "ControlledCheckpointStore",
                        source: Box::new(error),
                    })?;
            }
            Ok::<_, object_store::Error>(stream::iter(paths).then(move |path| {
                let inner = inner.clone();
                let fail =
                    fail_path.as_ref() == Some(&path) && fail_once.swap(false, Ordering::SeqCst);
                async move {
                    if fail {
                        return Err(object_store::Error::PermissionDenied {
                            path: path.to_string(),
                            source: Box::new(DeleteFailure),
                        });
                    }
                    inner.delete(&path).await?;
                    Ok(path)
                }
            }))
        })
        .try_flatten()
        .boxed()
    }

    fn list(&self, prefix: Option<&Path>) -> BoxStream<'static, object_store::Result<ObjectMeta>> {
        self.inner.list(prefix)
    }

    async fn list_with_delimiter(&self, prefix: Option<&Path>) -> object_store::Result<ListResult> {
        self.inner.list_with_delimiter(prefix).await
    }

    async fn copy_opts(
        &self,
        from: &Path,
        to: &Path,
        options: CopyOptions,
    ) -> object_store::Result<()> {
        self.inner.copy_opts(from, to, options).await
    }
}

use std::collections::HashMap;
use std::sync::Arc;

use datafusion::execution::runtime_env::RuntimeEnv;
use datafusion_common::{DataFusionError, Result, exec_err, plan_datafusion_err, plan_err};
use futures::TryStreamExt;
use object_store::path::Path;
use object_store::{ObjectStore, ObjectStoreExt, PutPayload};
use sail_common_datafusion::extension::SessionExtension;
use sail_object_store::resolve_object_store_path;
use tokio::sync::Mutex;
use url::Url;

use super::local::LocalRoot;
use super::plan::Row;
use super::proto::Request;
use super::proto::request::Verb;

const MARKER: &str = "_sail_graph_run";
const MAX_RUNS: usize = 1024;

#[derive(Debug)]
struct Run {
    uri: String,
    prefix: Path,
    token: String,
    released: bool,
}
#[derive(Debug, Default)]
struct State {
    runs: HashMap<String, Run>,
    closed: bool,
}

pub(crate) struct GraphRuns {
    root: String,
    prefix: Path,
    store: Arc<dyn ObjectStore>,
    local: Option<LocalRoot>,
    state: Mutex<State>,
}

impl std::fmt::Debug for GraphRuns {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("GraphRuns")
            .field("root", &self.root)
            .finish_non_exhaustive()
    }
}

impl SessionExtension for GraphRuns {
    fn name() -> &'static str {
        "GraphUtilsOwnedRuns"
    }
}

impl GraphRuns {
    pub(super) fn new(runtime: &RuntimeEnv, root: &str) -> Result<Self> {
        // Reject ambiguous spellings before URL parsing normalizes traversal.
        if root.len() > 4096
            || root.contains(['%', '\\', '?', '#'])
            || root.split('/').any(|s| s == "." || s == "..")
        {
            return plan_err!("graph utils root contains an ambiguous path");
        }
        let url = Url::parse(root).map_err(|e| plan_datafusion_err!("graph utils root: {e}"))?;
        if !url.username().is_empty()
            || url.password().is_some()
            || url.cannot_be_a_base()
            || url.path().trim_matches('/').is_empty()
        {
            return plan_err!("graph utils root must be an absolute URI with a non-root prefix");
        }
        if url.path().trim_matches('/').split('/').any(|s| {
            s.is_empty()
                || !s
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b"-_.=".contains(&b))
        }) {
            return plan_err!("graph utils root requires unambiguous ASCII path segments");
        }
        let (url, local) = LocalRoot::canonicalize(&url)?;
        let root = url.to_string().trim_end_matches('/').to_owned();
        let resolved = resolve_object_store_path(runtime, &root)?;
        Ok(Self {
            root,
            prefix: resolved.prefix().clone(),
            store: resolved.store().clone(),
            local,
            state: Mutex::new(State::default()),
        })
    }

    pub(super) fn validate(request: &Request) -> Result<()> {
        let Some(verb) = &request.verb else {
            return plan_err!("graph utils request has no verb");
        };
        match verb {
            Verb::Ping(p) if p.client_version.len() > 128 => {
                return plan_err!("client version too long");
            }
            Verb::Mkdir(m) => {
                uuid::Uuid::parse_str(&m.request_id)
                    .map_err(|_| plan_datafusion_err!("Mkdir.request_id must be a UUID"))?;
                if m.root.len() > 4096 {
                    return plan_err!("root URI too long");
                }
            }
            Verb::Ls(l) if l.limit > 1000 => return plan_err!("Ls.limit must be at most 1000"),
            _ => {}
        }
        Ok(())
    }

    fn owned_path(&self, run: &Run, path: &str) -> Result<Path> {
        if path.len() > 4096 || path.contains(['%', '\\', '?', '#']) {
            return plan_err!("invalid owned run path");
        }
        let path = path.trim_end_matches('/');
        if path == run.uri {
            return Ok(run.prefix.clone());
        }
        let suffix = path
            .strip_prefix(&format!("{}/", run.uri))
            .ok_or_else(|| plan_datafusion_err!("path is outside the token's owned run"))?;
        if suffix.split('/').any(|s| {
            s.is_empty()
                || s == "."
                || s == ".."
                || !s
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b"-_.=".contains(&b))
        }) {
            return plan_err!("owned run suffix must contain unambiguous ASCII path segments");
        }
        Ok(suffix
            .split('/')
            .fold(run.prefix.clone(), |path, segment| path.join(segment)))
    }

    async fn remove(&self, prefix: &Path) -> Result<i64> {
        self.check_local(prefix).await?;
        let mut listing = self.store.list(Some(prefix));
        let mut count = 0_i64;
        while let Some(entry) = listing.try_next().await? {
            match self.store.delete(&entry.location).await {
                Ok(()) => count += 1,
                Err(object_store::Error::NotFound { .. }) => {}
                Err(error) => return Err(DataFusionError::ObjectStore(Box::new(error))),
            }
        }
        Ok(count)
    }

    async fn check_local(&self, prefix: &Path) -> Result<()> {
        if let Some(local) = &self.local {
            let parts = prefix.prefix_match(&self.prefix).ok_or_else(|| {
                plan_datafusion_err!("local graph path is outside the staging root")
            })?;
            let relative = parts
                .map(|part| part.as_ref().to_string())
                .collect::<std::path::PathBuf>();
            local.check(relative).await?;
        }
        Ok(())
    }

    pub(super) async fn execute(&self, request: Request) -> Result<Vec<Row>> {
        Self::validate(&request)?;
        let Some(verb) = request.verb else {
            return exec_err!("graph utils request has no verb");
        };
        let mut state = self.state.lock().await;
        if state.closed {
            return exec_err!("graph utils session has closed");
        }
        match verb {
            Verb::Ping(_) => Ok(vec![Row {
                path: Some(self.root.clone()),
                capabilities: Some(r#"["fs","owned_runs_v1","axpb"]"#.into()),
                ..Row::new("pong")
            }]),
            Verb::Mkdir(request) => {
                if !request.root.is_empty() && request.root.trim_end_matches('/') != self.root {
                    return exec_err!("Mkdir.root differs from the configured trusted root");
                }
                let key = uuid::Uuid::parse_str(&request.request_id)
                    .map_err(|e| plan_datafusion_err!("request UUID: {e}"))?
                    .to_string();
                if !state.runs.contains_key(&key) {
                    if state.runs.len() >= MAX_RUNS {
                        return exec_err!("graph utils session reached the 1024 run limit");
                    }
                    let id = uuid::Uuid::new_v4().to_string();
                    let run = Run {
                        uri: format!("{}/{id}", self.root),
                        prefix: self.prefix.clone().join(id),
                        token: uuid::Uuid::new_v4().to_string(),
                        released: false,
                    };
                    // Record ownership before awaiting storage: cancelled allocation
                    // attempts remain discoverable by retry and session cleanup.
                    state.runs.insert(key.clone(), run);
                }
                let run = state
                    .runs
                    .get(&key)
                    .ok_or_else(|| plan_datafusion_err!("run missing"))?;
                if run.released {
                    return exec_err!("Mkdir request refers to a released run");
                }
                self.check_local(&run.prefix).await?;
                self.store
                    .put(
                        &run.prefix.clone().join(MARKER),
                        PutPayload::from_static(b"gf-utils-v1"),
                    )
                    .await?;
                Ok(vec![Row {
                    path: Some(run.uri.clone()),
                    token: Some(run.token.clone()),
                    ..Row::new("mkdir")
                }])
            }
            verb => {
                let (path, token) = match &verb {
                    Verb::Exists(v) => (&v.path, &v.token),
                    Verb::Ls(v) => (&v.path, &v.token),
                    Verb::Rm(v) => (&v.path, &v.token),
                    _ => return exec_err!("invalid filesystem verb"),
                };
                let run = state
                    .runs
                    .values_mut()
                    .find(|r| r.token == *token)
                    .ok_or_else(|| plan_datafusion_err!("unknown run token in this session"))?;
                let prefix = self.owned_path(run, path)?;
                if run.released && !matches!(verb, Verb::Rm(_)) {
                    return exec_err!("graph run has been released");
                }
                match verb {
                    Verb::Exists(request) => {
                        self.check_local(&prefix).await?;
                        let exists = self.store.list(Some(&prefix)).try_next().await?.is_some();
                        Ok(vec![Row {
                            path: Some(request.path),
                            value: Some(exists),
                            ..Row::new("exists")
                        }])
                    }
                    Verb::Ls(request) => {
                        self.check_local(&prefix).await?;
                        let limit = if request.limit == 0 {
                            100
                        } else {
                            request.limit
                        } as usize;
                        let mut listing = self.store.list(Some(&prefix));
                        let mut rows = vec![];
                        let mut truncated = false;
                        while let Some(entry) = listing.try_next().await? {
                            if entry.location == run.prefix.clone().join(MARKER) {
                                continue;
                            }
                            if rows.len() == limit {
                                truncated = true;
                                break;
                            }
                            let suffix = entry
                                .location
                                .as_ref()
                                .strip_prefix(run.prefix.as_ref())
                                .ok_or_else(|| {
                                    plan_datafusion_err!("store returned object outside owned run")
                                })?;
                            rows.push(Row {
                                path: Some(format!("{}{suffix}", run.uri)),
                                size: Some(
                                    i64::try_from(entry.size)
                                        .map_err(|e| plan_datafusion_err!("object size: {e}"))?,
                                ),
                                ..Row::new("entry")
                            });
                        }
                        rows.push(Row {
                            path: Some(request.path),
                            count: Some(rows.len() as i64),
                            truncated,
                            ..Row::new("ls")
                        });
                        Ok(rows)
                    }
                    Verb::Rm(request) => {
                        let count = if run.released {
                            0
                        } else {
                            self.remove(&prefix).await?
                        };
                        if prefix == run.prefix {
                            run.released = true;
                        }
                        Ok(vec![Row {
                            path: Some(request.path),
                            count: Some(count),
                            ..Row::new("rm")
                        }])
                    }
                    _ => exec_err!("invalid filesystem verb"),
                }
            }
        }
    }

    /// Best-effort cleanup after session teardown has requested executor/job
    /// shutdown. That shutdown is not a join barrier for every detached writer;
    /// interrupted writes can still require operator cleanup of late objects.
    /// Transient store failures get bounded retries, with every owned namespace
    /// attempted on each pass. The caller logs any error after exhaustion.
    pub(crate) async fn cleanup(&self) -> Result<()> {
        const ATTEMPTS: usize = 3;
        for attempt in 1..=ATTEMPTS {
            match self.cleanup_once().await {
                Ok(()) => return Ok(()),
                Err(error) if attempt == ATTEMPTS => {
                    return exec_err!("graph run cleanup exhausted {ATTEMPTS} attempts: {error}");
                }
                Err(error) => {
                    log::warn!("graph run cleanup attempt {attempt}/{ATTEMPTS} failed: {error}");
                    tokio::time::sleep(std::time::Duration::from_millis(200)).await;
                }
            }
        }
        Ok(())
    }

    async fn cleanup_once(&self) -> Result<()> {
        let mut state = self.state.lock().await;
        state.closed = true;
        let mut errors = vec![];
        for run in state.runs.values_mut() {
            match self.remove(&run.prefix).await {
                Ok(_) => run.released = true,
                Err(error) => errors.push(error.to_string()),
            }
        }
        if errors.is_empty() {
            Ok(())
        } else {
            exec_err!(
                "graph run cleanup failed for {} namespaces: {}",
                errors.len(),
                errors.join("; ")
            )
        }
    }
}

#![expect(
    clippy::expect_used,
    reason = "test fixtures assert their typed receipt contract"
)]

use std::sync::Arc;

use datafusion::execution::runtime_env::RuntimeEnv;
use datafusion::prelude::SessionContext;
use datafusion_common::Result;
use futures::TryStreamExt;
use object_store::memory::InMemory;
use object_store::path::Path;
use object_store::{ObjectStore, ObjectStoreExt, PutPayload};
use prost::Message;
use sail_common_datafusion::connect_extension::ConnectRelationHandler;

use super::plan::Handler;
use super::proto::request::Verb;
use super::proto::{Exists, Ls, Mkdir, Request, Rm};
use super::storage::GraphRuns;

fn request(verb: Verb) -> Request {
    Request { verb: Some(verb) }
}
fn mkdir(id: &str) -> Request {
    request(Verb::Mkdir(Mkdir {
        root: String::new(),
        request_id: id.into(),
    }))
}
fn fixture() -> Result<(Arc<GraphRuns>, Arc<InMemory>)> {
    let runtime = RuntimeEnv::default();
    let store = Arc::new(InMemory::new());
    runtime.register_object_store(
        &url::Url::parse("memory:///").expect("constant URL"),
        store.clone(),
    );
    Ok((
        Arc::new(GraphRuns::new(&runtime, "memory:///graphs")?),
        store,
    ))
}
async fn allocate(runs: &GraphRuns) -> Result<(String, String)> {
    let rows = runs
        .execute(mkdir(&uuid::Uuid::new_v4().to_string()))
        .await?;
    Ok((
        rows[0].path.clone().expect("path"),
        rows[0].token.clone().expect("token"),
    ))
}

#[tokio::test]
async fn planning_and_schema_analysis_have_no_storage_effects() -> Result<()> {
    let (runs, store) = fixture()?;
    let handler = Handler { runs, driver: None };
    let provider = handler.plan(
        &mkdir(&uuid::Uuid::new_v4().to_string()).encode_to_vec(),
        vec![],
    )?;
    assert_eq!(provider.schema().field(0).name(), "kind");
    let session = SessionContext::new();
    let plan = provider.scan(&session.state(), None, &[], None).await?;
    assert!(store.list(None).try_next().await?.is_none());
    let batches = datafusion::physical_plan::collect(plan, session.task_ctx()).await?;
    assert_eq!(batches[0].num_rows(), 1);
    assert!(store.list(None).try_next().await?.is_some());
    Ok(())
}

#[tokio::test]
async fn allocation_retry_and_release_are_session_owned_and_idempotent() -> Result<()> {
    let (runs, store) = fixture()?;
    let id = uuid::Uuid::new_v4().to_string();
    let first = runs.execute(mkdir(&id)).await?;
    let second = runs.execute(mkdir(&id)).await?;
    assert_eq!(first[0].path, second[0].path);
    assert_eq!(first[0].token, second[0].token);
    let path = first[0].path.clone().expect("path");
    let token = first[0].token.clone().expect("token");
    let exists = request(Verb::Exists(Exists {
        path: path.clone(),
        token: token.clone(),
    }));
    assert_eq!(runs.execute(exists.clone()).await?[0].value, Some(true));
    let remove = request(Verb::Rm(Rm { path, token }));
    assert_eq!(runs.execute(remove.clone()).await?[0].count, Some(1));
    assert_eq!(runs.execute(remove).await?[0].count, Some(0));
    assert!(runs.execute(mkdir(&id)).await.is_err());
    assert!(runs.execute(exists).await.is_err());
    assert!(store.list(None).try_next().await?.is_none());
    Ok(())
}

#[tokio::test]
async fn capabilities_reject_other_runs_roots_traversal_and_sessions() -> Result<()> {
    let (runs, _) = fixture()?;
    let (path, token) = allocate(&runs).await?;
    let (other, _) = allocate(&runs).await?;
    for invalid in [
        "memory:///graphs".to_string(),
        other,
        format!("{path}extra"),
        format!("{path}/../escape"),
        format!("{path}/%2e%2e/escape"),
        format!("{path}/a//b"),
        format!("{path}/a\\b"),
        format!("{path}/stage?query"),
    ] {
        assert!(
            runs.execute(request(Verb::Rm(Rm {
                path: invalid,
                token: token.clone()
            })))
            .await
            .is_err()
        );
    }
    let (other_session, _) = fixture()?;
    assert!(
        other_session
            .execute(request(Verb::Rm(Rm { path, token })))
            .await
            .is_err()
    );
    Ok(())
}

#[tokio::test]
async fn bounded_listing_and_session_cleanup_preserve_foreign_objects() -> Result<()> {
    let (runs, store) = fixture()?;
    let (path, token) = allocate(&runs).await?;
    let prefix = path.strip_prefix("memory:///").expect("memory URI");
    for suffix in [
        "stage-1/part-1.parquet",
        "stage-1/part-2.parquet",
        "stage-2/part-1.parquet",
        "stage-10/part-1.parquet",
    ] {
        store
            .put(
                &Path::from(format!("{prefix}/{suffix}")),
                PutPayload::from_static(b"test"),
            )
            .await?;
    }
    store
        .put(
            &Path::from("graphs/unowned/keep"),
            PutPayload::from_static(b"keep"),
        )
        .await?;
    let rows = runs
        .execute(request(Verb::Ls(Ls {
            path: path.clone(),
            token: token.clone(),
            limit: 1,
        })))
        .await?;
    assert_eq!(rows.len(), 2);
    assert_eq!(rows[0].kind, "entry");
    assert_eq!(rows[1].kind, "ls");
    assert_eq!(rows[1].count, Some(1));
    assert!(rows[1].truncated);
    let removed = runs
        .execute(request(Verb::Rm(Rm {
            path: format!("{path}/stage-1"),
            token: token.clone(),
        })))
        .await?;
    assert_eq!(removed[0].count, Some(2));
    assert!(
        store
            .head(&Path::from(format!("{prefix}/stage-10/part-1.parquet")))
            .await
            .is_ok()
    );
    assert_eq!(
        runs.execute(request(Verb::Exists(Exists {
            path: path.clone(),
            token
        })))
        .await?[0]
            .value,
        Some(true)
    );
    runs.cleanup().await?;
    let remaining = store.list(None).try_collect::<Vec<_>>().await?;
    assert_eq!(remaining.len(), 1);
    assert_eq!(remaining[0].location, Path::from("graphs/unowned/keep"));
    assert!(allocate(&runs).await.is_err());
    Ok(())
}

#[test]
fn request_limits_and_root_spelling_are_validated() -> Result<()> {
    let (runs, _) = fixture()?;
    let handler = Handler { runs, driver: None };
    assert!(handler.plan(&[0; 8193], vec![]).is_err());
    assert!(handler.plan(&[], vec![]).is_err());
    assert!(GraphRuns::validate(&mkdir("not-a-uuid")).is_err());
    assert!(
        GraphRuns::validate(&request(Verb::Ls(Ls {
            path: String::new(),
            token: String::new(),
            limit: 1001
        })))
        .is_err()
    );
    for invalid in [
        "/tmp/root",
        "file:///",
        "file:///a/../b",
        "file:///a/%2e",
        "file:///a?b",
        "file:///a#b",
    ] {
        assert!(GraphRuns::new(&RuntimeEnv::default(), invalid).is_err());
    }
    Ok(())
}

#[tokio::test]
async fn graph_scalar_codec_and_signed_null_semantics() -> Result<()> {
    use datafusion_common::ScalarValue;
    use datafusion_expr::lit;

    let session = SessionContext::new();
    let mut functions = vec![];
    for function in super::functions::register()? {
        let mut bytes = vec![];
        assert!(sail_common_datafusion::native_scalar::encode_scalar(
            &function, &mut bytes
        )?);
        let decoded =
            sail_common_datafusion::native_scalar::decode_scalar(function.name(), &bytes)?;
        session.register_udf((*decoded).clone());
        functions.push(decoded);
    }
    let batches = session
        .read_empty()?
        .select(vec![
            functions[0]
                .call(vec![lit(i64::MIN), lit(2_i64), lit(0_i64)])
                .alias("a"),
            functions[0]
                .call(vec![lit(ScalarValue::Int64(None)), lit(1_i64), lit(0_i64)])
                .alias("b"),
            functions[1].call(vec![]).alias("v"),
        ])?
        .collect()
        .await?;
    let batch = &batches[0];
    use datafusion::arrow::array::{Array, Int64Array};
    assert_eq!(
        batch
            .column(0)
            .as_any()
            .downcast_ref::<Int64Array>()
            .expect("int64")
            .value(0),
        27
    );
    assert!(batch.column(1).is_null(0));
    Ok(())
}

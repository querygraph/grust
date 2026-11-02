use datafusion::catalog::{TableFunctionArgs, TableFunctionImpl};
use datafusion_expr::TableSource;
use sail_common_datafusion::datasource::{DataSource, SinkInfo, SourceInfo};

use super::*;

fn empty_table() -> Result<Arc<dyn TableProvider>> {
    Ok(Arc::new(MemTable::try_new(
        Arc::new(Schema::new(vec![Field::new("id", DataType::Int64, false)])),
        vec![vec![]],
    )?))
}
struct CheckingSource {
    resources: Option<Arc<TaskResourceScope>>,
}
#[tonic::async_trait]
impl DataSource for CheckingSource {
    fn name(&self) -> &str {
        "read_probe"
    }
    async fn create_source(
        &self,
        session: &dyn Session,
        info: SourceInfo,
    ) -> Result<Arc<dyn TableSource>> {
        assert_eq!(info.paths, ["input"]);
        let store = session
            .runtime_env()
            .object_store(ObjectStoreUrl::parse("memory://resolver")?)?;
        if let Some(expected) = &self.resources {
            let scope = session.extension::<TaskResourceScope>()?;
            assert!(Arc::ptr_eq(&scope, expected));
            assert!(Arc::ptr_eq(
                &session.task_ctx().extension::<TaskResourceScope>()?,
                expected
            ));
            assert_eq!(session.config().target_partitions(), 7);
            let value =
                scope
                    .run(move |_| async move {
                        Ok(store.get(&Path::from("input")).await?.bytes().await?)
                    })
                    .await?;
            assert_eq!(value.as_ref(), b"admitted");
        } else {
            assert!(session.extension::<TaskResourceScope>().is_err());
            assert_eq!(session.config().target_partitions(), 9);
            assert_eq!(
                store
                    .get(&Path::from("input"))
                    .await?
                    .bytes()
                    .await?
                    .as_ref(),
                b"parent"
            );
        }
        Ok(provider_as_source(empty_table()?))
    }
    async fn create_writer(&self, _: &dyn Session, _: SinkInfo) -> Result<LogicalPlan> {
        datafusion_common::internal_err!("read-only test source")
    }
}
async fn source_read(scoped: bool, format_path: bool) -> TestResult {
    let fixture = Fixture::new().await?;
    fixture
        .ctx
        .extension::<DataSourceRegistry>()?
        .register_data_source(Arc::new(CheckingSource {
            resources: scoped.then(|| fixture.resources.clone()),
        }))?;
    let resolver = if scoped {
        fixture.resolver()
    } else {
        PlanResolver::new(&fixture.ctx, Arc::new(PlanConfig::default()))
    };
    let plan = if format_path {
        resolver
            .resolve_query_read_named_table(
                spec::ReadNamedTable {
                    name: vec!["read_probe", "input"].into(),
                    temporal: None,
                    sample: None,
                    options: vec![],
                },
                &mut PlanResolverState::new(),
                false,
            )
            .await?
    } else {
        resolver
            .resolve_query_read_data_source(
                spec::ReadDataSource {
                    format: Some("read_probe".into()),
                    schema: None,
                    options: vec![],
                    paths: vec!["input".into()],
                    predicates: vec![],
                },
                &mut PlanResolverState::new(),
            )
            .await?
    };
    assert_eq!(plan.schema().fields().len(), 1);
    assert_eq!(
        fixture.calls.load(Ordering::SeqCst),
        0,
        "factory must run before physical planning"
    );
    assert_eq!(
        fixture.resources.drain().await?.registered,
        usize::from(scoped)
    );
    assert!(fixture.ctx.extension::<TaskResourceScope>().is_err());
    Ok(())
}
#[tokio::test]
async fn source_factory_gets_captured_session_before_physical_planning() -> TestResult {
    source_read(true, false).await
}
#[tokio::test]
async fn format_path_factory_gets_captured_session() -> TestResult {
    source_read(true, true).await
}
#[tokio::test]
async fn source_factory_without_view_keeps_authoritative_session() -> TestResult {
    source_read(false, false).await
}
#[derive(Debug)]
struct CheckingFunction(Arc<TaskResourceScope>);
impl TableFunctionImpl for CheckingFunction {
    fn call_with_args(&self, args: TableFunctionArgs) -> Result<Arc<dyn TableProvider>> {
        let session = args.session();
        let scope = session.extension::<TaskResourceScope>()?;
        assert!(Arc::ptr_eq(&scope, &self.0));
        assert_eq!(session.config().target_partitions(), 7);
        let store = session
            .runtime_env()
            .object_store(ObjectStoreUrl::parse("memory://resolver")?)?;
        scope.spawn(move |_| async move {
            let value = store.get(&Path::from("input")).await?.bytes().await?;
            assert_eq!(value.as_ref(), b"admitted");
            Ok(())
        })?;
        empty_table()
    }
}
#[tokio::test]
async fn native_table_function_lookup_stays_authoritative_but_factory_gets_view() -> TestResult {
    let fixture = Fixture::new().await?;
    // Lookup deliberately stays authoritative: register after the view captured
    // its state. Only the provider callback receives the selected Session.
    fixture.ctx.register_udtf(
        "read_probe",
        Arc::new(CheckingFunction(fixture.resources.clone())),
    );
    let plan = fixture
        .resolver()
        .resolve_query_read_udtf(
            spec::ReadUdtf {
                name: spec::ObjectName::bare("read_probe"),
                arguments: vec![],
                named_arguments: vec![],
                options: vec![],
            },
            &mut PlanResolverState::new(),
        )
        .await?;
    assert_eq!(plan.schema().fields().len(), 1);
    assert_eq!(fixture.calls.load(Ordering::SeqCst), 0);
    assert_eq!(fixture.resources.drain().await?.registered, 1);
    assert!(fixture.ctx.extension::<TaskResourceScope>().is_err());
    Ok(())
}

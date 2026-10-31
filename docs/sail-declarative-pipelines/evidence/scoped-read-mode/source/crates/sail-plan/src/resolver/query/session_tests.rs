use std::collections::HashMap;
use std::sync::Arc;
use std::sync::atomic::{AtomicUsize, Ordering};

use arrow::array::{Int64Array, RecordBatch};
use arrow::datatypes::{DataType, Field, Schema, SchemaRef};
use datafusion::catalog::Session;
use datafusion::datasource::{MemTable, TableProvider, provider_as_source};
use datafusion::execution::SessionStateBuilder;
use datafusion::execution::context::QueryPlanner;
use datafusion::execution::object_store::{
    DefaultObjectStoreRegistry, ObjectStoreRegistry, ObjectStoreUrl,
};
use datafusion::optimizer::AnalyzerRule;
use datafusion::physical_plan::ExecutionPlan;
use datafusion::physical_planner::{DefaultPhysicalPlanner, PhysicalPlanner};
use datafusion::prelude::{SessionConfig, SessionContext};
use datafusion_common::{Result, ScalarValue};
use datafusion_expr::{Expr, LogicalPlan, LogicalPlanBuilder, TableType, lit};
use object_store::ObjectStoreExt;
use object_store::memory::InMemory;
use object_store::path::Path;
use sail_catalog::manager::{CatalogManager, CatalogManagerOptions};
use sail_catalog::provider::CatalogProvider;
use sail_catalog_memory::MemoryCatalogProvider;
use sail_common::spec;
use sail_common_datafusion::catalog::display::DefaultCatalogDisplay;
use sail_common_datafusion::datasource::DataSourceRegistry;
use sail_common_datafusion::extension::SessionExtensionAccessor;
use sail_common_datafusion::session::plan::PlanService;
use sail_common_datafusion::session::scoped::ScopedSession;
use sail_common_datafusion::task_resources::TaskResourceScope;
use tokio::runtime::Handle;

use crate::catalog::SparkCatalogObjectDisplay;
use crate::config::PlanConfig;
use crate::error::PlanResult;
use crate::formatter::SparkPlanFormatter;
use crate::resolver::PlanResolver;
use crate::resolver::scope::RelationScope;
use crate::resolver::state::PlanResolverState;

type TestResult = std::result::Result<(), Box<dyn std::error::Error>>;

#[derive(Debug)]
struct CheckingPlanner {
    resources: Arc<TaskResourceScope>,
    calls: Arc<AtomicUsize>,
}
#[tonic::async_trait]
impl QueryPlanner for CheckingPlanner {
    async fn create_physical_plan(
        &self,
        plan: &LogicalPlan,
        session: &dyn Session,
    ) -> Result<Arc<dyn ExecutionPlan>> {
        assert!(Arc::ptr_eq(
            &session.extension::<TaskResourceScope>()?,
            &self.resources
        ));
        assert_eq!(session.config().target_partitions(), 7);
        self.calls.fetch_add(1, Ordering::SeqCst);
        DefaultPhysicalPlanner::default()
            .create_physical_plan(plan, session)
            .await
    }
}

#[derive(Debug)]
struct CheckingTable {
    schema: SchemaRef,
    resources: Arc<TaskResourceScope>,
}
#[tonic::async_trait]
impl TableProvider for CheckingTable {
    fn schema(&self) -> SchemaRef {
        self.schema.clone()
    }
    fn table_type(&self) -> TableType {
        TableType::Base
    }
    async fn scan(
        &self,
        session: &dyn Session,
        projection: Option<&Vec<usize>>,
        filters: &[Expr],
        limit: Option<usize>,
    ) -> Result<Arc<dyn ExecutionPlan>> {
        let resources = session.extension::<TaskResourceScope>()?;
        assert!(Arc::ptr_eq(&resources, &self.resources));
        assert!(Arc::ptr_eq(
            &session.task_ctx().extension::<TaskResourceScope>()?,
            &resources
        ));
        let store = session
            .runtime_env()
            .object_store(ObjectStoreUrl::parse("memory://resolver")?)?;
        let value = resources
            .run(move |_| async move { Ok(store.get(&Path::from("input")).await?.bytes().await?) })
            .await?;
        assert_eq!(value.as_ref(), b"admitted");
        let batch = RecordBatch::try_new(
            self.schema.clone(),
            vec![
                Arc::new(Int64Array::from(vec![1, 2, 2])),
                Arc::new(Int64Array::from(vec![10, 20, 10])),
            ],
        )?;
        MemTable::try_new(self.schema.clone(), vec![vec![batch]])?
            .scan(session, projection, filters, limit)
            .await
    }
}
struct Inputs(LogicalPlan);
impl RelationScope for Inputs {
    fn resolve(&self, name: &[String]) -> PlanResult<Option<LogicalPlan>> {
        assert_eq!(name, ["input"]);
        Ok(Some(self.0.clone()))
    }
}
struct Fixture {
    ctx: SessionContext,
    session: ScopedSession,
    inputs: Inputs,
    resources: Arc<TaskResourceScope>,
    calls: Arc<AtomicUsize>,
}
impl Fixture {
    async fn new() -> TestResultWith<Self> {
        Self::with_analyzer(None).await
    }
    async fn with_analyzer(
        rule: Option<Arc<dyn AnalyzerRule + Send + Sync>>,
    ) -> TestResultWith<Self> {
        let resources = Arc::new(TaskResourceScope::new(Handle::current()));
        let calls = Arc::new(AtomicUsize::new(0));
        let provider = MemoryCatalogProvider::new("catalog".into(), vec!["db"].try_into()?, None);
        let catalog = CatalogManager::try_new(CatalogManagerOptions {
            catalogs: HashMap::from([(
                "catalog".into(),
                Arc::new(provider) as Arc<dyn CatalogProvider>,
            )]),
            default_catalog: "catalog".into(),
            default_database: vec!["db".into()],
            global_temporary_database: vec!["global_temp".into()],
        })?;
        let config = SessionConfig::new()
            .with_target_partitions(7)
            .with_create_default_catalog_and_schema(false)
            .with_extension(Arc::new(catalog))
            .with_extension(Arc::new(DataSourceRegistry::new()))
            .with_extension(Arc::new(PlanService::new(
                Box::new(DefaultCatalogDisplay::<SparkCatalogObjectDisplay>::default()),
                Box::new(SparkPlanFormatter),
            )));
        let builder = SessionStateBuilder::new()
            .with_config(config)
            .with_default_features()
            .with_query_planner(Arc::new(CheckingPlanner {
                resources: resources.clone(),
                calls: calls.clone(),
            }));
        let builder = match rule {
            Some(rule) => builder.with_analyzer_rules(vec![rule]),
            None => builder,
        };
        let ctx = SessionContext::new_with_state(builder.build());
        let original = Arc::new(InMemory::new());
        original.put(&Path::from("input"), "parent".into()).await?;
        let url = ObjectStoreUrl::parse("memory://resolver")?;
        ctx.runtime_env()
            .register_object_store(url.as_ref(), original);
        let child = Arc::new(InMemory::new());
        child.put(&Path::from("input"), "admitted".into()).await?;
        let registry = Arc::new(DefaultObjectStoreRegistry::new());
        registry.register_store(url.as_ref(), child);
        let session = ScopedSession::new(ctx.state(), resources.clone())
            .with_object_store_registry(registry)?;
        // The caller chooses a snapshot after authority mutation. Later changes
        // to that authority must not replace the supplied Session mid-helper.
        ctx.state_ref()
            .write()
            .config_mut()
            .options_mut()
            .execution
            .target_partitions = 9;
        let table = CheckingTable {
            schema: Arc::new(Schema::new(vec![
                Field::new("a", DataType::Int64, false),
                Field::new("b", DataType::Int64, false),
            ])),
            resources: resources.clone(),
        };
        let logical = LogicalPlanBuilder::scan("input", provider_as_source(Arc::new(table)), None)?
            .build()?;
        Ok(Self {
            ctx,
            session,
            inputs: Inputs(logical),
            resources,
            calls,
        })
    }
    fn resolver(&self) -> PlanResolver<'_> {
        PlanResolver::new(&self.ctx, Arc::new(PlanConfig::default()))
            .with_relation_scope(&self.inputs)
            .with_query_session(&self.session)
    }
    async fn check(&self, registered: usize) -> TestResult {
        assert_eq!(self.calls.load(Ordering::SeqCst), 1);
        assert_eq!(self.resources.drain().await?.registered, registered);
        assert!(self.ctx.extension::<TaskResourceScope>().is_err());
        assert_eq!(self.ctx.state().config().target_partitions(), 9);
        Ok(())
    }
}
type TestResultWith<T> = std::result::Result<T, Box<dyn std::error::Error>>;
fn input() -> spec::QueryPlan {
    spec::QueryPlan::new(spec::QueryNode::Read {
        read_type: spec::ReadType::NamedTable(Box::new(spec::ReadNamedTable {
            name: spec::ObjectName::bare("input"),
            temporal: None,
            sample: None,
            options: vec![],
        })),
        is_streaming: false,
    })
}
fn attribute(name: &str) -> spec::Expr {
    spec::Expr::UnresolvedAttribute {
        name: spec::ObjectName::bare(name),
        plan_id: None,
        is_metadata_column: false,
    }
}
#[tokio::test]
async fn tail_count_uses_supplied_session() -> TestResult {
    let fixture = Fixture::new().await?;
    let plan = fixture
        .resolver()
        .resolve_query_tail(
            input(),
            spec::Expr::Literal(spec::Literal::Int64 { value: Some(1) }),
            &mut PlanResolverState::new(),
        )
        .await?;
    let LogicalPlan::Limit(limit) = plan else {
        return Err("tail did not resolve to Limit".into());
    };
    assert_eq!(limit.skip.as_deref(), Some(&lit(2i64)));
    fixture.check(1).await
}
#[tokio::test]
async fn pivot_inference_uses_supplied_session() -> TestResult {
    let fixture = Fixture::new().await?;
    let count = sail_sql_analyzer::expression::from_ast_expression(
        sail_sql_analyzer::parser::parse_expression("count(*)")?,
    )?;
    let plan = fixture
        .resolver()
        .resolve_query_pivot(
            spec::Pivot {
                input: Box::new(input()),
                grouping: Some(vec![]),
                aggregate: vec![count],
                columns: vec![attribute("b")],
                values: vec![],
            },
            &mut PlanResolverState::new(),
        )
        .await?;
    assert_eq!(plan.schema().fields().len(), 2);
    fixture.check(1).await
}
#[tokio::test]
async fn crosstab_distinct_values_use_supplied_session() -> TestResult {
    let fixture = Fixture::new().await?;
    let plan = fixture
        .resolver()
        .resolve_query_stat_cross_tab(
            input(),
            "a".into(),
            "b".into(),
            &mut PlanResolverState::new(),
        )
        .await?;
    assert_eq!(plan.schema().fields().len(), 3);
    fixture.check(1).await
}
#[tokio::test]
async fn time_travel_scalar_uses_supplied_session() -> TestResult {
    let fixture = Fixture::new().await?;
    let options = fixture
        .resolver()
        .resolve_time_travel_options(
            "delta",
            Some(spec::TableTemporal::Version {
                value: spec::Expr::Literal(spec::Literal::Int64 { value: Some(3) }),
            }),
            &mut PlanResolverState::new(),
        )
        .await?;
    assert_eq!(options, vec![("versionAsOf".into(), "3".into())]);
    fixture.check(0).await
}
#[tokio::test]
async fn absent_query_session_keeps_legacy_collection_path() -> TestResult {
    let ctx = SessionContext::new();
    let resolver = PlanResolver::new(&ctx, Arc::new(PlanConfig::default()));
    let batches = resolver
        .collect_query(
            LogicalPlanBuilder::empty(true)
                .project(vec![lit(7i64)])?
                .build()?,
        )
        .await?;
    assert_eq!(
        ScalarValue::try_from_array(batches[0].column(0).as_ref(), 0)?,
        ScalarValue::Int64(Some(7))
    );
    assert!(ctx.extension::<TaskResourceScope>().is_err());
    Ok(())
}

#[path = "factory_session_tests.rs"]
mod factories;

#[path = "write_factory_session_tests.rs"]
mod writers;

#[path = "lake_metadata_session_tests.rs"]
mod lake_metadata;

#[path = "row_factory_session_tests.rs"]
mod row_factories;

#[path = "delta_metadata_session_tests.rs"]
mod delta_metadata;

#[path = "procedure_factory_session_tests.rs"]
mod procedures;

#[path = "generated_analyzer_session_tests.rs"]
mod generated_analyzer;

#[path = "view_publication_tests.rs"]
mod view_publication;

#[path = "read_case_tests.rs"]
mod read_case;

#[path = "late_bound_scope_tests.rs"]
mod late_bound_scope;

#[derive(Debug, PartialEq)]
struct ScopedRead {
    name: Vec<String>,
    streaming: bool,
    late: bool,
}
struct ModeInputs {
    plan: LogicalPlan,
    reads: std::sync::Mutex<Vec<ScopedRead>>,
}
impl ModeInputs {
    fn record(
        &self,
        name: &[String],
        streaming: bool,
        late: bool,
    ) -> PlanResult<Option<LogicalPlan>> {
        self.reads
            .lock()
            .map_err(|e| crate::error::PlanError::internal(e.to_string()))?
            .push(ScopedRead {
                name: name.to_vec(),
                streaming,
                late,
            });
        Ok(Some(self.plan.clone()))
    }
}
impl RelationScope for ModeInputs {
    fn resolve(&self, _: &[String]) -> PlanResult<Option<LogicalPlan>> {
        Err(crate::error::PlanError::internal("read mode bypassed"))
    }
    fn resolve_read(&self, name: &[String], streaming: bool) -> PlanResult<Option<LogicalPlan>> {
        self.record(name, streaming, false)
    }
    fn resolve_late_bound_read(
        &self,
        name: &[String],
        streaming: bool,
    ) -> PlanResult<Option<LogicalPlan>> {
        self.record(name, streaming, true)
    }
}

#[tokio::test]
async fn scoped_named_and_computed_reads_preserve_mode_and_binding_phase() -> TestResult {
    let fixture = Fixture::new().await?;
    let inputs = ModeInputs {
        plan: fixture.inputs.0.clone(),
        reads: Default::default(),
    };
    let resolver = PlanResolver::new(&fixture.ctx, Arc::new(PlanConfig::default()))
        .with_relation_scope(&inputs);
    let mut expected = vec![];
    for streaming in [false, true] {
        for late in [false, true] {
            let read_type = if late {
                spec::ReadType::DynamicTable(Box::new(spec::ReadDynamicTable {
                    name: sail_sql_analyzer::expression::from_ast_expression(
                        sail_sql_analyzer::parser::parse_expression("'input'")?,
                    )?,
                    sample: None,
                    options: vec![],
                }))
            } else {
                spec::ReadType::NamedTable(Box::new(spec::ReadNamedTable {
                    name: spec::ObjectName::bare("input"),
                    temporal: None,
                    sample: None,
                    options: vec![],
                }))
            };
            resolver
                .resolve_named_plan(spec::Plan::Query(spec::QueryPlan::new(
                    spec::QueryNode::Read {
                        read_type,
                        is_streaming: streaming,
                    },
                )))
                .await?;
            expected.push(ScopedRead {
                name: vec!["input".into()],
                streaming,
                late,
            });
        }
    }
    let cte = sail_sql_analyzer::statement::from_ast_statement(
        sail_sql_analyzer::parser::parse_one_statement(
            "WITH input AS (SELECT 1 AS id) SELECT * FROM input",
        )?,
    )?;
    resolver.resolve_named_plan(cte).await?;
    assert_eq!(
        *inputs.reads.lock().map_err(|_| "reads poisoned")?,
        expected,
        "CTE lookup must precede a scope read"
    );
    // A legacy scope which only implements resolve still handles both modes.
    for streaming in [false, true] {
        let mut query = input();
        let spec::QueryNode::Read { is_streaming, .. } = &mut query.node else {
            return Err("fixture read missing".into());
        };
        *is_streaming = streaming;
        fixture
            .resolver()
            .resolve_named_plan(spec::Plan::Query(query))
            .await?;
    }
    assert_eq!(fixture.calls.load(Ordering::SeqCst), 0);
    Ok(())
}

#[tokio::test]
async fn stored_view_scope_forwards_read_mode_and_namespace() -> TestResult {
    let fixture = Fixture::new().await?;
    let inputs = ModeInputs {
        plan: fixture.inputs.0.clone(),
        reads: Default::default(),
    };
    let manager = fixture.ctx.extension::<CatalogManager>()?;
    let properties = vec![
        ("view.catalogAndNamespace.numParts".into(), "2".into()),
        ("view.catalogAndNamespace.part.0".into(), "catalog".into()),
        ("view.catalogAndNamespace.part.1".into(), "db".into()),
    ];
    let scope = crate::resolver::scope::ViewScope::from_properties(
        manager.as_ref(),
        Some(&inputs),
        &properties,
    )?
    .ok_or("view scope missing")?;
    let mut expected = vec![];
    for streaming in [false, true] {
        scope.resolve_read(&["input".into()], streaming)?;
        scope.resolve_late_bound_read(&["input".into()], streaming)?;
        for late in [false, true] {
            expected.push(ScopedRead {
                name: vec!["catalog".into(), "db".into(), "input".into()],
                streaming,
                late,
            });
        }
    }
    assert_eq!(
        *inputs.reads.lock().map_err(|_| "reads poisoned")?,
        expected
    );
    Ok(())
}

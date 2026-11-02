//! Characterize artifacts before introducing finite analysis/attempt owners.
use std::collections::HashMap;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, Mutex, Weak};

use datafusion::arrow::array::{Int64Array, RecordBatch};
use datafusion::arrow::datatypes::{DataType, Field, Schema, SchemaRef};
use datafusion::catalog::Session;
use datafusion::common::tree_node::{TreeNode, TreeNodeRecursion};
use datafusion::common::{Result, internal_datafusion_err};
use datafusion::datasource::{MemTable, TableProvider, provider_as_source};
use datafusion::logical_expr::{Expr, LogicalPlan, TableSource, TableType};
use datafusion::physical_plan::ExecutionPlan;
use sail_common::spec;
use sail_common_datafusion::datasource::{DataSource, DataSourceRegistry, SinkInfo, SourceInfo};

use super::*;
use crate::pipelines::graph::PipelineGraph;
use crate::pipelines::sql;
use crate::spark::connect::pipeline_command as pc;

type TestResult = std::result::Result<(), Box<dyn std::error::Error>>;

#[derive(Debug)]
struct ProbeTable {
    _lease: Arc<()>,
    scans: Arc<AtomicUsize>,
}
#[tonic::async_trait]
impl TableProvider for ProbeTable {
    fn schema(&self) -> SchemaRef {
        Arc::new(Schema::new(vec![Field::new("id", DataType::Int64, false)]))
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
        self.scans.fetch_add(1, Ordering::SeqCst);
        let batch = RecordBatch::try_new(
            self.schema(),
            vec![Arc::new(Int64Array::from(vec![1, 2, 3]))],
        )?;
        MemTable::try_new(self.schema(), vec![vec![batch]])?
            .scan(session, projection, filters, limit)
            .await
    }
}
struct ProbeSource {
    leases: Arc<Mutex<Vec<Weak<()>>>>,
    scans: Arc<AtomicUsize>,
    reject: bool,
}
#[tonic::async_trait]
impl DataSource for ProbeSource {
    fn name(&self) -> &str {
        "artifact_probe"
    }
    async fn create_source(
        &self,
        _: &dyn Session,
        info: SourceInfo,
    ) -> Result<Arc<dyn TableSource>> {
        assert_eq!(info.paths, ["input"]);
        if self.reject {
            return Err(internal_datafusion_err!(
                "source unavailable after analysis"
            ));
        }
        let lease = Arc::new(());
        self.leases
            .lock()
            .map_err(|_| internal_datafusion_err!("probe leases poisoned"))?
            .push(Arc::downgrade(&lease));
        Ok(provider_as_source(Arc::new(ProbeTable {
            _lease: lease,
            scans: self.scans.clone(),
        })))
    }
    async fn create_writer(&self, _: &dyn Session, _: SinkInfo) -> Result<LogicalPlan> {
        Err(internal_datafusion_err!(
            "artifact analysis must not create a writer"
        ))
    }
}
async fn definition(
    text: &str,
) -> crate::error::SparkResult<crate::pipelines::graph::GraphDefinition> {
    let mut graph = PipelineGraph::new("test_catalog".into(), "test_db".into(), HashMap::new());
    sql::prepare(
        pc::DefineSqlGraphElements {
            sql_text: Some(text.into()),
            ..Default::default()
        },
        |_| async {
            Err(crate::error::SparkError::internal(
                "no catalog expression in fixture",
            ))
        },
    )
    .await?
    .commit(&mut graph)?;
    Ok(graph.definition)
}
async fn retention(text: &str) -> TestResult {
    let ctx = sql::tests::resolution_context()?;
    let leases = Arc::new(Mutex::new(vec![]));
    let scans = Arc::new(AtomicUsize::new(0));
    let registry = DataSourceRegistry::new();
    registry.register_data_source(Arc::new(ProbeSource {
        leases: leases.clone(),
        scans: scans.clone(),
        reject: false,
    }))?;
    ctx.state_ref()
        .write()
        .config_mut()
        .set_extension(Arc::new(registry));
    let graph = definition(text).await?;
    let analyzed = analyze(&ctx, &graph).await?;
    let leases = leases.lock().map_err(|_| "probe leases poisoned")?;
    assert_eq!(
        leases.len(),
        1,
        "only the external definition creates a provider"
    );
    assert!(
        leases[0].upgrade().is_none(),
        "exported analysis artifact retained provider"
    );
    assert_eq!(scans.load(Ordering::SeqCst), 0);
    for output in &graph.outputs {
        let schema = analyzed
            .schemas
            .get(&output.name)
            .ok_or("analyzed output missing")?;
        assert_eq!(schema.field(0).name(), "id");
    }
    drop(analyzed);
    assert!(leases[0].upgrade().is_none());
    Ok(())
}
#[tokio::test]
async fn analysis_temporary_view_exports_schema_without_provider() -> TestResult {
    retention("CREATE TEMPORARY VIEW temp AS SELECT * FROM artifact_probe.`input`; CREATE MATERIALIZED VIEW target AS SELECT * FROM temp").await
}
#[tokio::test]
async fn analysis_materialized_table_exports_schema_without_provider() -> TestResult {
    retention("CREATE MATERIALIZED VIEW target AS SELECT * FROM artifact_probe.`input`").await
}
#[tokio::test]
async fn analysis_persisted_view_exports_schema_without_provider() -> TestResult {
    retention("CREATE VIEW target AS SELECT * FROM artifact_probe.`input`").await
}
#[tokio::test]
async fn analysis_temporary_clock_remains_unfolded() -> TestResult {
    let ctx = sql::tests::resolution_context()?;
    let graph = definition("CREATE TEMPORARY VIEW temp AS SELECT current_timestamp() AS clock; CREATE MATERIALIZED VIEW target AS SELECT * FROM temp").await?;
    let spark = ctx.extension::<crate::session::SparkSession>()?;
    let named = sail_plan::resolver::PlanResolver::new(&ctx, spark.plan_config()?)
        .resolve_named_plan(spec::Plan::Query(graph.flows[0].query.clone()))
        .await?;
    let plan = &named.plan;
    let mut clocks = 0;
    plan.apply(|node| {
        for expr in node.expressions() {
            if expr.exists(|expr| Ok(matches!(expr, Expr::ScalarFunction(function) if function.func.name() == "timestamp_now")))? {
                clocks += 1;
            }
        }
        Ok(TreeNodeRecursion::Continue)
    })?;
    assert_eq!(
        clocks, 1,
        "normal graph resolution must not fold the clock at analysis time"
    );
    drop(named);
    let analyzed = analyze(&ctx, &graph).await?;
    let schema = analyzed
        .schemas
        .get(&vec!["temp".into()])
        .ok_or("temporary schema missing")?;
    assert!(matches!(
        schema.field(0).data_type(),
        DataType::Timestamp(..)
    ));
    Ok(())
}

#[tokio::test]
async fn temporary_working_plan_remains_available_for_analysis_helper_execution() -> TestResult {
    view_working_plan_remains_available("TEMPORARY VIEW").await
}

#[tokio::test]
async fn persisted_working_plan_remains_available_for_analysis_helper_execution() -> TestResult {
    view_working_plan_remains_available("VIEW").await
}

async fn view_working_plan_remains_available(kind: &str) -> TestResult {
    let ctx = crate::pipelines::catalog_preparation_tests::context()?;
    let leases = Arc::new(Mutex::new(vec![]));
    let scans = Arc::new(AtomicUsize::new(0));
    let registry = DataSourceRegistry::new();
    registry.register_data_source(Arc::new(ProbeSource {
        leases: leases.clone(),
        scans: scans.clone(),
        reject: false,
    }))?;
    ctx.state_ref()
        .write()
        .config_mut()
        .set_extension(Arc::new(registry));
    let mut graph = definition(&format!("CREATE {kind} temp AS SELECT * FROM artifact_probe.`input`; CREATE MATERIALIZED VIEW target AS SELECT * FROM temp")).await?;
    let read = graph.flows[1].query.clone();
    graph.flows[1].query = spec::QueryPlan::new(spec::QueryNode::Tail {
        input: Box::new(read),
        limit: spec::Expr::Literal(spec::Literal::Int64 { value: Some(1) }),
    });
    let analyzed = analyze(&ctx, &graph).await?;
    assert_eq!(
        scans.load(Ordering::SeqCst),
        1,
        "tail's analysis-time count must see the working provider plan"
    );
    assert_eq!(analyzed.schemas.len(), 2);
    assert!(
        leases
            .lock()
            .map_err(|_| "probe leases poisoned")?
            .iter()
            .all(|lease| lease.upgrade().is_none())
    );
    ctx.extension::<sail_common_datafusion::session::job::JobService>()?
        .runner()
        .stop()
        .await?;
    Ok(())
}

#[tokio::test]
async fn persisted_view_publishes_captured_columns_after_source_is_unavailable() -> TestResult {
    let ctx = crate::pipelines::catalog_preparation_tests::context()?;
    let leases = Arc::new(Mutex::new(vec![]));
    let scans = Arc::new(AtomicUsize::new(0));
    let registry = DataSourceRegistry::new();
    registry.register_data_source(Arc::new(ProbeSource {
        leases: leases.clone(),
        scans: scans.clone(),
        reject: false,
    }))?;
    ctx.state_ref()
        .write()
        .config_mut()
        .set_extension(Arc::new(registry));
    let graph = definition("CREATE VIEW target (captured COMMENT 'column comment') COMMENT 'view comment' AS SELECT id FROM artifact_probe.`input`").await?;
    let analyzed = analyze(&ctx, &graph).await?;
    let options = analyzed
        .publications
        .get(&graph.outputs[0].name)
        .ok_or("view publication missing")?
        .clone();
    assert_eq!(options.columns[0].name, "captured");
    assert_eq!(options.columns[0].data_type, DataType::Int64);
    assert!(!options.columns[0].nullable);
    assert_eq!(
        options.columns[0].comment.as_deref(),
        Some("column comment")
    );
    assert!(
        leases
            .lock()
            .map_err(|_| "probe leases poisoned")?
            .iter()
            .all(|lease| lease.upgrade().is_none())
    );
    let unavailable = DataSourceRegistry::new();
    unavailable.register_data_source(Arc::new(ProbeSource {
        leases,
        scans: scans.clone(),
        reject: true,
    }))?;
    ctx.state_ref()
        .write()
        .config_mut()
        .set_extension(Arc::new(unavailable));
    crate::pipelines::materialize::views(&ctx, &graph, &analyzed).await?;
    let status = ctx
        .extension::<sail_catalog::manager::CatalogManager>()?
        .get_table_or_view(&graph.outputs[0].name)
        .await?;
    let sail_common_datafusion::catalog::TableKind::View {
        definition,
        columns,
        comment,
        properties,
    } = status.kind
    else {
        return Err("published target is not a view".into());
    };
    assert_eq!(definition, options.definition);
    assert_eq!(columns[0].name, options.columns[0].name);
    assert_eq!(columns[0].data_type, options.columns[0].data_type);
    assert_eq!(columns[0].nullable, options.columns[0].nullable);
    assert_eq!(columns[0].comment, options.columns[0].comment);
    assert_eq!(comment, options.comment);
    assert_eq!(properties, options.properties);
    assert_eq!(scans.load(Ordering::SeqCst), 0);
    ctx.extension::<sail_common_datafusion::session::job::JobService>()?
        .runner()
        .stop()
        .await?;
    Ok(())
}

#[tokio::test]
async fn resolution_errors_precede_flow_type_and_multi_query_validation() -> TestResult {
    let ctx = sql::tests::resolution_context()?;
    ctx.state_ref()
        .write()
        .config_mut()
        .set_extension(Arc::new(DataSourceRegistry::new()));
    for query in [
        "SELECT * FROM missing_source",
        "SELECT missing_column FROM range(1)",
    ] {
        let mut graph = definition(&format!("CREATE MATERIALIZED VIEW target AS {query}")).await?;
        let query_errors =
            |error: AnalysisError| -> Result<Vec<String>, Box<dyn std::error::Error>> {
                let AnalysisError::Unresolved(failures) = error else {
                    return Err(format!("query failure was not aggregated: {error}").into());
                };
                assert!(failures.downstream.is_empty());
                Ok(failures
                    .direct
                    .into_values()
                    .map(|error| error.to_string())
                    .collect())
            };
        let expected = match analyze(&ctx, &graph).await {
            Err(error) => query_errors(error)?.remove(0),
            Ok(_) => return Err("invalid source unexpectedly resolved".into()),
        };
        assert!(
            expected.contains(if query.contains("missing_source") {
                "missing_source"
            } else {
                "missing_column"
            }),
            "fixture did not reach query analysis: {expected}"
        );
        graph.outputs[0].kind = OutputType::Table;
        let actual = match analyze(&ctx, &graph).await {
            Err(error) => query_errors(error)?,
            Ok(_) => return Err("invalid streaming-table source unexpectedly resolved".into()),
        };
        assert_eq!(
            actual.as_slice(),
            std::slice::from_ref(&expected),
            "flow type masked query analysis: {query}"
        );

        graph.outputs[0].kind = OutputType::MaterializedView;
        let mut extra = graph.flows[0].clone();
        extra.name = vec!["extra".into()];
        graph.flows.push(extra);
        let actual = match analyze(&ctx, &graph).await {
            Err(error) => query_errors(error)?,
            Ok(_) => return Err("invalid multi-query source unexpectedly resolved".into()),
        };
        assert_eq!(
            actual,
            [expected.clone(), expected],
            "flow count masked query analysis: {query}"
        );
    }
    Ok(())
}

#[tokio::test]
async fn unresolved_flows_collect_independent_and_transitive_failures() -> TestResult {
    let ctx = sql::tests::resolution_context()?;
    ctx.state_ref()
        .write()
        .config_mut()
        .set_extension(Arc::new(DataSourceRegistry::new()));
    let graph = definition("CREATE MATERIALIZED VIEW leaf AS SELECT * FROM middle; CREATE MATERIALIZED VIEW bad AS SELECT * FROM missing_source; CREATE MATERIALIZED VIEW middle AS SELECT * FROM bad; CREATE MATERIALIZED VIEW other_bad AS SELECT missing_column FROM range(1); CREATE MATERIALIZED VIEW healthy AS SELECT 1 AS id").await?;
    let Some(AnalysisError::Unresolved(failures)) = analyze(&ctx, &graph).await.err() else {
        return Err("expected unresolved-flow report".into());
    };
    assert_eq!(
        failures
            .direct
            .keys()
            .map(|name| name.last().map(String::as_str))
            .collect::<Vec<_>>(),
        [Some("bad"), Some("other_bad")]
    );
    assert_eq!(
        failures
            .downstream
            .keys()
            .map(|name| name.last().map(String::as_str))
            .collect::<Vec<_>>(),
        [Some("leaf"), Some("middle")]
    );
    let events: Vec<_> = failures.events().collect();
    assert_eq!(events.len(), 4);
    assert!(
        events[..2]
            .iter()
            .all(|event| event.starts_with("Failed to resolve flow due to upstream failure:"))
    );
    assert!(events[2].contains("missing_source"));
    assert!(events[3].contains("missing_column"));
    use tonic_types::StatusExt;
    let status: tonic::Status = failures.into_error().into();
    let details = status.get_error_details();
    let info = details
        .error_info()
        .ok_or("missing unresolved-pipeline ErrorInfo")?;
    assert_eq!(
        info.reason,
        "org.apache.spark.sql.pipelines.graph.UnresolvedPipelineException"
    );
    assert_eq!(
        serde_json::from_str::<Vec<String>>(&info.metadata["classes"])?,
        [
            "org.apache.spark.sql.pipelines.graph.UnresolvedPipelineException",
            "org.apache.spark.sql.AnalysisException",
            "java.lang.Exception",
            "java.lang.Throwable",
            "java.lang.Object"
        ]
    );
    for absent in ["errorClass", "sqlState", "messageParameters"] {
        assert!(!info.metadata.contains_key(absent));
    }
    Ok(())
}

#[tokio::test]
async fn successful_producer_of_failed_output_is_not_a_failed_flow() -> TestResult {
    let ctx = sql::tests::resolution_context()?;
    ctx.state_ref()
        .write()
        .config_mut()
        .set_extension(Arc::new(DataSourceRegistry::new()));
    let mut graph = definition("CREATE MATERIALIZED VIEW bad AS SELECT * FROM missing_source; CREATE MATERIALIZED VIEW consumer AS SELECT * FROM bad; CREATE MATERIALIZED VIEW healthy AS SELECT 1 AS id").await?;
    let mut good = graph.flows[2].clone();
    good.name = vec!["successful_producer".into()];
    good.target = graph.outputs[0].name.clone();
    graph.flows.push(good);
    let Some(AnalysisError::Unresolved(failures)) = analyze(&ctx, &graph).await.err() else {
        return Err("expected unresolved-flow report".into());
    };
    assert_eq!(failures.direct.len(), 1);
    assert!(failures.direct.contains_key(&graph.flows[0].name));
    assert_eq!(failures.downstream.len(), 1);
    assert!(failures.downstream.contains_key(&graph.flows[1].name));
    assert!(!failures.to_string().contains("successful_producer"));
    Ok(())
}

#[tokio::test]
async fn unresolved_report_releases_working_providers_without_scanning() -> TestResult {
    let ctx = sql::tests::resolution_context()?;
    let leases = Arc::new(Mutex::new(vec![]));
    let scans = Arc::new(AtomicUsize::new(0));
    let registry = DataSourceRegistry::new();
    registry.register_data_source(Arc::new(ProbeSource {
        leases: leases.clone(),
        scans: scans.clone(),
        reject: false,
    }))?;
    ctx.state_ref()
        .write()
        .config_mut()
        .set_extension(Arc::new(registry));
    let graph = definition("CREATE MATERIALIZED VIEW source AS SELECT * FROM artifact_probe.`input`; CREATE MATERIALIZED VIEW invalid AS SELECT missing_column FROM source").await?;
    let Some(AnalysisError::Unresolved(failures)) = analyze(&ctx, &graph).await.err() else {
        return Err("expected unresolved-flow report".into());
    };
    assert_eq!(failures.direct.len(), 1);
    assert!(failures.downstream.is_empty());
    let leases = leases.lock().map_err(|_| "probe leases poisoned")?;
    assert_eq!(leases.len(), 1);
    assert!(
        leases[0].upgrade().is_none(),
        "failure report retained working provider"
    );
    assert_eq!(scans.load(Ordering::SeqCst), 0);
    Ok(())
}

#[tokio::test]
async fn unresolved_query_precedes_persisted_view_source_restrictions() -> TestResult {
    let ctx = sql::tests::resolution_context()?;
    ctx.state_ref()
        .write()
        .config_mut()
        .set_extension(Arc::new(DataSourceRegistry::new()));
    for text in [
        "CREATE TEMPORARY VIEW temporary AS SELECT 1 AS id; CREATE VIEW persisted AS SELECT * FROM temporary; CREATE MATERIALIZED VIEW missing AS SELECT * FROM missing_source",
        "CREATE MATERIALIZED VIEW missing AS SELECT * FROM missing_source; CREATE TEMPORARY VIEW temporary AS SELECT 1 AS id; CREATE VIEW persisted AS SELECT * FROM temporary",
    ] {
        let graph = definition(text).await?;
        let Some(AnalysisError::Unresolved(failures)) = analyze(&ctx, &graph).await.err() else {
            return Err("persisted-view validation masked query resolution".into());
        };
        assert_eq!(
            failures
                .direct
                .keys()
                .map(|name| name.last().map(String::as_str))
                .collect::<Vec<_>>(),
            [Some("missing")]
        );
        assert!(failures.downstream.is_empty());
        assert!(
            failures
                .direct
                .values()
                .all(|error| error.to_string().contains("missing_source"))
        );
    }
    Ok(())
}

#[tokio::test]
async fn virtual_schema_errors_follow_actual_reads_and_unresolved_queries() -> TestResult {
    let ctx = sql::tests::resolution_context()?;
    ctx.state_ref()
        .write()
        .config_mut()
        .set_extension(Arc::new(DataSourceRegistry::new()));
    for declared in [false, true] {
        for read in [false, true] {
            for missing in ["none", "first", "last"] {
                if missing == "none" && (declared || !read) {
                    // These three graphs force schemas after query resolution;
                    // their raw final merge diagnostic has a separate contract.
                    continue;
                }
                let mut statements = vec![
                    "CREATE MATERIALIZED VIEW events_int AS SELECT 1 AS id".to_string(),
                    "CREATE MATERIALIZED VIEW events_str AS SELECT 'x' AS id".to_string(),
                    format!(
                        "CREATE STREAMING TABLE merged{}",
                        if declared { " (id INT)" } else { "" }
                    ),
                    "CREATE FLOW merged_int AS INSERT INTO merged BY NAME SELECT * FROM STREAM(events_int)".to_string(),
                    "CREATE FLOW merged_str AS INSERT INTO merged BY NAME SELECT * FROM STREAM(events_str)".to_string(),
                ];
                if read {
                    statements
                        .push("CREATE MATERIALIZED VIEW consumer AS SELECT id FROM merged".into());
                    statements.push(
                        "CREATE MATERIALIZED VIEW downstream AS SELECT * FROM consumer".into(),
                    );
                }
                let bad =
                    "CREATE MATERIALIZED VIEW late AS SELECT * FROM missing_source".to_string();
                match missing {
                    "first" => statements.insert(0, bad),
                    "last" => statements.push(bad),
                    _ => {}
                }
                let graph = definition(&statements.join(";")).await?;
                let Some(AnalysisError::Unresolved(failures)) = analyze(&ctx, &graph).await.err()
                else {
                    return Err(format!("expected unresolved report: declared={declared}, read={read}, missing={missing}").into());
                };
                let direct: Vec<_> = failures
                    .direct
                    .keys()
                    .filter_map(|name| name.last().map(String::as_str))
                    .collect();
                let mut expected = vec![];
                if read && !declared {
                    expected.push("consumer");
                }
                if missing != "none" {
                    expected.push("late");
                }
                assert_eq!(
                    direct, expected,
                    "declared={declared}, read={read}, missing={missing}"
                );
                let downstream: Vec<_> = failures
                    .downstream
                    .keys()
                    .filter_map(|name| name.last().map(String::as_str))
                    .collect();
                assert_eq!(
                    downstream,
                    if read && !declared {
                        vec!["downstream"]
                    } else {
                        vec![]
                    }
                );
                for (name, error) in &failures.direct {
                    if name.last().is_some_and(|name| name == "consumer") {
                        assert!(
                            error
                                .to_string()
                                .contains("UNABLE_TO_INFER_PIPELINE_TABLE_SCHEMA")
                        );
                    }
                }
            }
        }
    }
    Ok(())
}

use std::sync::Mutex;

use datafusion::prelude::SessionContext;
use sail_catalog::error::{CatalogError, CatalogObject};
use sail_catalog::manager::CatalogManager;
use sail_common::spec;
use sail_common_datafusion::catalog::{PartitionTransform, TableKind};
use sail_common_datafusion::datasource::DataSourceRegistry;
use sail_common_datafusion::extension::SessionExtensionAccessor;
use sail_plan::error::PlanError;

use super::analysis::{AnalyzedGraph, GraphScope};
use super::execution::run_command;
use super::graph::{GraphDefinition, analysis, quoted};
use super::selection::Selection;
use crate::error::{SparkError, SparkResult};
use crate::session::SparkSession;
use crate::spark::connect::{OutputType, pipeline_command as pc};

/// Materialize the selected table metadata before executing any batch flow,
/// matching Spark's DatasetManager. A failed write can leave an empty target.
pub(super) async fn tables(
    ctx: &SessionContext,
    graph: &GraphDefinition,
    analyzed: &AnalyzedGraph,
    selection: &Selection,
) -> SparkResult<()> {
    let manager = ctx.extension::<CatalogManager>()?;
    let planning = ctx
        .extension::<SparkSession>()?
        .planning_context(ctx, graph.sql_conf.clone())?;
    let ctx = &planning.context;
    let config = planning.config;
    for output in &graph.outputs {
        if output.kind != OutputType::MaterializedView
            || output.view.is_some()
            || !selection.runs(&output.name)
        {
            continue;
        }
        let details = match &output.definition.details {
            Some(pc::define_output::Details::TableDetails(details)) => details.clone(),
            _ => pc::define_output::TableDetails::default(),
        };
        let mut properties =
            super::properties::canonicalize(details.table_properties.into_iter().collect())?;
        for (key, value) in [
            ("comment", output.definition.comment.as_ref()),
            ("provider", details.format.as_ref()),
        ] {
            if let Some(value) = value {
                if properties
                    .get(key)
                    .is_some_and(|previous| previous != value)
                {
                    return Err(SparkError::invalid(format!(
                        "For dataset {}, {key} '{value}' does not match its reserved table property",
                        quoted(&output.name)
                    )));
                }
                properties.insert(key.to_string(), value.clone());
            }
        }
        if !details.clustering_columns.is_empty() {
            if !details.partition_cols.is_empty() {
                return Err(analysis(
                    "SPECIFY_CLUSTER_BY_WITH_PARTITIONED_BY_IS_NOT_ALLOWED",
                    quoted(&output.name),
                ));
            }
            return Err(SparkError::unsupported("pipeline table clustering"));
        }
        let schema = analyzed
            .relations
            .get(&output.name)
            .ok_or_else(|| SparkError::internal("analyzed output missing"))?
            .schema()
            .as_arrow();
        let columns = super::schema::table_columns(output, schema)?;
        let table: spec::ObjectName = output.name.clone().into();
        let existing = match manager.get_table_or_view(&output.name).await {
            Ok(status) => Some(status),
            Err(CatalogError::NotFound(CatalogObject::Table | CatalogObject::View, _)) => None,
            Err(error) => return Err(PlanError::from(error).into()),
        };
        if let Some(existing) = existing {
            let TableKind::Table {
                columns: old_columns,
                partition_by,
                ..
            } = existing.kind
            else {
                return Err(analysis(
                    "EXPECT_TABLE_NOT_VIEW.NO_ALTERNATIVE",
                    quoted(&output.name),
                ));
            };
            if partition_by.len() != details.partition_cols.len()
                || partition_by
                    .iter()
                    .zip(&details.partition_cols)
                    .any(|(old, new)| {
                        old.column != *new
                            || !matches!(old.transform, None | Some(PartitionTransform::Identity))
                    })
            {
                return Err(analysis(
                    "CANNOT_UPDATE_PARTITION_COLUMNS",
                    quoted(&output.name),
                ));
            }
            run_command(
                ctx,
                config.clone(),
                spec::CommandNode::TruncateTable {
                    table: table.clone(),
                },
                None,
            )
            .await?;
            let mut changes = vec![];
            for column in &columns {
                if let Some(old) = old_columns.iter().find(|old| old.name == column.name) {
                    let old_type: spec::DataType =
                        crate::spark::connect::DataType::try_from(old.data_type.clone())?
                            .try_into()?;
                    if old_type != column.data_type {
                        run_command(
                            ctx,
                            config.clone(),
                            spec::CommandNode::AlterTable {
                                table: table.clone(),
                                if_exists: false,
                                operation: spec::AlterTableOperation::AlterColumnType {
                                    name: spec::ObjectName::bare(column.name.clone()),
                                    data_type: column.data_type.clone(),
                                },
                            },
                            None,
                        )
                        .await?;
                    }
                    if old.nullable != column.nullable {
                        changes.push(spec::ColumnChange::Nullability {
                            path: vec![column.name.clone()],
                            nullable: column.nullable,
                        });
                    }
                    if old.comment != column.comment {
                        changes.push(spec::ColumnChange::Comment {
                            path: vec![column.name.clone()],
                            comment: column.comment.clone(),
                        });
                    }
                } else {
                    changes.push(spec::ColumnChange::Add {
                        path: vec![column.name.clone()],
                        data_type: column.data_type.clone(),
                        nullable: column.nullable,
                        comment: column.comment.clone(),
                        default: None,
                        position: None,
                    });
                }
            }
            for column in &old_columns {
                if !columns.iter().any(|new| new.name == column.name) {
                    changes.push(spec::ColumnChange::Drop {
                        path: vec![column.name.clone()],
                        if_exists: false,
                    });
                }
            }
            if !changes.is_empty() {
                run_command(
                    ctx,
                    config.clone(),
                    spec::CommandNode::AlterTable {
                        table: table.clone(),
                        if_exists: false,
                        operation: spec::AlterTableOperation::AlterColumns { changes },
                    },
                    None,
                )
                .await?;
            }
            if !properties.is_empty() {
                run_command(
                    ctx,
                    config.clone(),
                    spec::CommandNode::AlterTable {
                        table,
                        if_exists: false,
                        operation: spec::AlterTableOperation::SetTableProperties {
                            properties: properties.into_iter().collect(),
                        },
                    },
                    None,
                )
                .await?;
            }
        } else {
            let format = properties
                .get("provider")
                .cloned()
                .unwrap_or_else(|| config.default_table_file_format.clone());
            ctx.extension::<DataSourceRegistry>()?
                .get_data_source(&format.to_ascii_lowercase())?;
            let definition = spec::TableDefinition {
                external: false,
                columns,
                comment: properties.get("comment").cloned(),
                constraints: vec![],
                location: None,
                file_format: Some(spec::TableFileFormat::General { format }),
                row_format: None,
                partition_by: details
                    .partition_cols
                    .into_iter()
                    .map(|name| {
                        spec::PartitionColumn::Expression(spec::Expr::UnresolvedAttribute {
                            name: spec::ObjectName::bare(name),
                            plan_id: None,
                            is_metadata_column: false,
                        })
                    })
                    .collect(),
                sort_by: vec![],
                bucket_by: None,
                cluster_by: vec![],
                mode: spec::CreateTableMode::Create,
                options: vec![],
                properties: properties.into_iter().collect(),
            };
            run_command(
                ctx,
                config.clone(),
                spec::CommandNode::CreateTable { table, definition },
                None,
            )
            .await?;
        }
    }
    Ok(())
}

/// Publish every persisted view from its analyzed definition, regardless of
/// table refresh selection. An excluded upstream table need not exist yet.
pub(super) async fn views(
    ctx: &SessionContext,
    graph: &GraphDefinition,
    analyzed: &AnalyzedGraph,
) -> SparkResult<()> {
    let spark = ctx.extension::<SparkSession>()?;
    for name in &analyzed.order {
        let output = graph
            .outputs
            .iter()
            .find(|output| &output.name == name)
            .ok_or_else(|| SparkError::internal("analyzed output missing"))?;
        let Some(mut definition) = output.view.clone() else {
            continue;
        };
        let flow = graph
            .flows
            .iter()
            .find(|flow| &flow.target == name)
            .ok_or_else(|| analysis("PIPELINE_DATASET_WITHOUT_FLOW", quoted(name)))?;
        let scope = GraphScope {
            graph,
            resolved: &analyzed.relations,
            reads: Mutex::default(),
            flow,
        };
        definition.replace = true;
        definition.if_not_exists = false;
        let planning = spark.planning_context(ctx, flow.sql_conf.clone())?;
        run_command(
            &planning.context,
            planning.config,
            spec::CommandNode::CreateView {
                view: name.clone().into(),
                definition,
            },
            Some(&scope),
        )
        .await?;
    }
    Ok(())
}

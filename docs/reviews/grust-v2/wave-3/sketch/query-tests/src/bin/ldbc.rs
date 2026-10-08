//! Compile unchanged SNB text against supplied schema/statistics, without reading graph data.
use grust_backend::query::{QueryStorage, SailSql};
use grust_cypher_frontend::{CypherLowering, CypherParser};
use grust_functions::*;
use grust_lpg::{GroupId, LogicalType, Schema};
use grust_optimized_plan::Estimate;
use grust_optimizer::query::{explain, HashJoinCost, JoinOptimizer};
use grust_optimizer::{DegreeSummary, Statistics};
use grust_resolution::{query::QueryResolver, Catalog, Context, ParameterTypes, ResolveError};
use grust_resolved_plan::query::Column;
use grust_resolved_plan::query::{Expr, Value};
use grust_syntax::parse_and_lower;
use grust_unresolved_plan::{GraphRef, Literal};
use serde::Deserialize;
use std::collections::HashMap;
#[derive(Deserialize)]
struct Request {
    schema: Schema,
    tables: Vec<Table>,
    queries: Vec<Query>,
    dataset_sha256: String,
}
#[derive(Deserialize)]
struct Table {
    group: u64,
    name: String,
    rows: u64,
    distinct: HashMap<String, u64>,
    source_ndv: Option<u64>,
    target_ndv: Option<u64>,
}
#[derive(Deserialize)]
struct Query {
    name: String,
    text: String,
    text_sha256: String,
    parameters: HashMap<String, i64>,
    expected: serde_json::Value,
    ordered: bool,
}
struct Dataset<'a>(&'a Request);
impl Catalog for Dataset<'_> {
    fn graph(&self, graph: &GraphRef) -> Result<(&str, &Schema), ResolveError> {
        match graph {
            GraphRef::Default => Ok(("snb-v1", &self.0.schema)),
            GraphRef::Named { namespace, name } if namespace.is_empty() && name == "snb-v1" => {
                Ok(("snb-v1", &self.0.schema))
            }
            _ => Err(ResolveError::UnknownGraph(graph.clone())),
        }
    }
}
struct Parameters<'a>(&'a HashMap<String, i64>);
impl ParameterTypes for Parameters<'_> {
    fn parameter(&self, name: &str) -> Option<(LogicalType, bool)> {
        self.0
            .contains_key(name)
            .then_some((LogicalType::Int64, false))
    }
}
impl QueryStorage for Dataset<'_> {
    fn table(&self, _: &str, group: GroupId) -> Option<Vec<String>> {
        self.0
            .tables
            .iter()
            .find(|t| t.group == group.0)
            .map(|t| vec![t.name.clone()])
    }
    fn column(&self, _: &str, _: GroupId, column: &Column) -> Option<String> {
        Some(match column {
            Column::Identity => "_identity".into(),
            Column::Source => "src".into(),
            Column::Target => "dst".into(),
            Column::Property(name) => name.clone(),
        })
    }
    fn function(&self, f: &FunctionDescriptor) -> Option<Vec<String>> {
        if f.provider != "snb-sail" {
            return None;
        }
        match f.name.name.as_str() {
            "coalesce" => Some(vec!["coalesce".into()]),
            "toInteger" => Some(vec!["bigint".into()]),
            _ => None,
        }
    }
}
impl Statistics for Dataset<'_> {
    fn revision(&self) -> Option<&str> {
        Some(&self.0.dataset_sha256)
    }
    fn rows(&self, _: &str, group: GroupId) -> Estimate<u64> {
        self.0
            .tables
            .iter()
            .find(|t| t.group == group.0)
            .map(|t| Estimate::Known(t.rows))
            .unwrap_or(Estimate::Unknown)
    }
    fn distinct(&self, _: &str, group: GroupId, name: &str) -> Estimate<u64> {
        self.0
            .tables
            .iter()
            .find(|t| t.group == group.0)
            .and_then(|t| t.distinct.get(name))
            .copied()
            .map(Estimate::Known)
            .unwrap_or(Estimate::Unknown)
    }
    fn degree(&self, _: &str, _: GroupId) -> Estimate<DegreeSummary> {
        Estimate::Unknown
    }
    fn endpoint_distinct(&self, _: &str, group: GroupId, source: bool) -> Estimate<u64> {
        self.0
            .tables
            .iter()
            .find(|t| t.group == group.0)
            .and_then(|t| if source { t.source_ndv } else { t.target_ndv })
            .map(Estimate::Known)
            .unwrap_or(Estimate::Unknown)
    }
}
fn registry() -> Registry {
    let mut registry = Registry::default();
    for (name, args, result, nulls) in [
        (
            "coalesce",
            vec![ArgumentType::Exact(LogicalType::String); 2],
            LogicalType::String,
            NullSemantics::ProviderDefined,
        ),
        (
            "toInteger",
            vec![ArgumentType::Exact(LogicalType::Int64)],
            LogicalType::Int64,
            NullSemantics::Strict,
        ),
    ] {
        registry
            .register(FunctionDescriptor {
                name: FunctionName::new(name),
                kind: FunctionKind::Scalar,
                signature: Signature {
                    arguments: args,
                    variadic: None,
                    result: ReturnType::Exact(result),
                },
                nulls,
                backends: BackendSupport::Named(vec!["sail".into()]),
                volatility: Volatility::Immutable,
                provider: "snb-sail".into(),
            })
            .unwrap();
    }
    registry
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let path = std::env::args().nth(1).ok_or("usage: ldbc request.json")?;
    let request: Request = serde_json::from_slice(&std::fs::read(path)?)?;
    let dataset = Dataset(&request);
    let registry = registry();
    let mut records = Vec::new();
    for query in &request.queries {
        let start = std::time::Instant::now();
        let unresolved = parse_and_lower(
            &CypherParser,
            &CypherLowering {
                functions: &registry,
            },
            &query.text,
        )
        .map_err(|e| format!("{}: {e:?}", query.name))?;
        let parameters = Parameters(&query.parameters);
        let plan = QueryResolver
            .resolve_iterative(
                &unresolved,
                &Context {
                    catalog: &dataset,
                    functions: &registry,
                    parameters: &parameters,
                },
                &grust_resolution::query::providers::NoProviders,
            )
            .map_err(|e| format!("{}: {e:?}", query.name))?;
        let values = query
            .parameters
            .iter()
            .map(|(name, v)| {
                (
                    name.clone(),
                    Expr {
                        kind: Value::Literal(Literal::Integer(*v)),
                        ty: Some(LogicalType::Int64),
                        nullable: false,
                    },
                )
            })
            .collect();
        let adapter = SailSql {
            storage: &dataset,
            parameters: &values,
        };
        let output_types = plan
            .output()
            .iter()
            .map(|f| grust_query_qualification::wire::spark_type(&f.ty))
            .collect::<Vec<_>>();
        let program = adapter.emit_program(&plan)?;
        let optimized = JoinOptimizer {
            statistics: Some(&dataset),
            cost: &HashJoinCost,
            max_relations: 8,
        }
        .optimize(plan);
        let optimized_program = adapter.emit_program(&optimized.logical)?;
        records.push(serde_json::json!({"name":query.name,"query_text":query.text,"query_sha256":query.text_sha256,"parameters":query.parameters,"sql":program.sql,"optimized_sql":optimized_program.sql,"traversals":grust_query_qualification::wire::traversals(&program.traversals),"steps":grust_query_qualification::wire::execution_steps(&program.steps),"optimized_traversals":grust_query_qualification::wire::traversals(&optimized_program.traversals),"optimized_steps":grust_query_qualification::wire::execution_steps(&optimized_program.steps),"expected":query.expected,"ordered":query.ordered,"output_types":output_types,"trace":optimized.trace,"estimated_cost":optimized.estimated_cost,"statistics_revision":optimized.statistics_revision,"explain":explain(&optimized),"compile_seconds":start.elapsed().as_secs_f64()}));
    }
    println!("{}", serde_json::to_string_pretty(&records)?);
    Ok(())
}

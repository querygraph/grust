use grust_backend::query::SailSql;
use grust_optimizer::query::{explain, HashJoinCost, JoinOptimizer};
use grust_query_qualification::fixtures::*;
use grust_resolution::{query::QueryResolver, Context};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let catalog = FixtureCatalog::default();
    let registry = registry();
    let params = values();
    let context = Context {
        catalog: &catalog,
        functions: &registry,
        parameters: &Parameters,
    };
    let mut records = Vec::new();
    let detailed_explain = std::env::args().any(|arg| arg == "--explain");
    let iterative = std::env::args().any(|arg| arg == "--iterative");
    let cases = if iterative {
        grust_query_qualification::iterative_cases::cases()
    } else {
        cases()
    };
    for case in cases {
        let plan = if iterative {
            QueryResolver.resolve_iterative(&case.plan, &context, &RelationPlugins)
        } else {
            QueryResolver.resolve_with_providers(&case.plan, &context, &RelationPlugins)
        }
        .map_err(|e| format!("{}: {e:?}", case.name))?;
        let output_types = plan
            .output()
            .iter()
            .map(|f| spark_type(&f.ty))
            .collect::<Vec<_>>();
        let program = SailSql {
            storage: &Storage,
            parameters: &params,
        }
        .emit_program(&plan)?;
        let optimized = JoinOptimizer {
            statistics: Some(&Stats),
            cost: &HashJoinCost,
            max_relations: 8,
        }
        .optimize(plan);
        let optimized_program = SailSql {
            storage: &Storage,
            parameters: &params,
        }
        .emit_program(&optimized.logical)?;
        records.push(serde_json::json!({"name":case.name,"sql":program.sql,"optimized_sql":optimized_program.sql,"traversals":traversals(&program.traversals),"optimized_traversals":traversals(&optimized_program.traversals),"expected":case.expected,"ordered":case.ordered,"output_types":output_types,"trace":optimized.trace,"explain":if detailed_explain {Some(explain(&optimized))} else {None}}));
    }
    println!("{}", serde_json::to_string_pretty(&records)?);
    Ok(())
}

fn spark_type(ty: &grust_lpg::LogicalType) -> String {
    use grust_lpg::LogicalType as T;
    if grust_resolved_plan::query::is_null_type(ty) {
        return "void".into();
    }
    match ty {
        T::Boolean => "boolean".into(),
        T::Int64 => "bigint".into(),
        T::Int32 => "int".into(),
        T::Float64 => "double".into(),
        T::Float32 => "float".into(),
        T::String => "string".into(),
        T::Binary => "binary".into(),
        T::List(t) => format!("array<{}>", spark_type(t)),
        T::Struct(fields) => format!(
            "struct<{}>",
            fields
                .iter()
                .map(|f| format!("{}:{}", f.name, spark_type(&f.ty)))
                .collect::<Vec<_>>()
                .join(",")
        ),
        _ => format!("{ty:?}"),
    }
}

fn traversals(steps: &[grust_backend::query::program::TraversalStep]) -> serde_json::Value {
    serde_json::Value::Array(steps.iter().map(|s| serde_json::json!({"view":s.view,"seed_sql":s.seed_sql,"adjacency_sql":s.adjacency_sql,"min_hops":s.min_hops,"max_hops":s.max_hops,"mode":format!("{:?}",s.mode),"shortest_walk":s.shortest_walk})).collect())
}

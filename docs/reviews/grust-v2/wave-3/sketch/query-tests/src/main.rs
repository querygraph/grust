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
    for case in cases() {
        let plan = QueryResolver
            .resolve(&case.plan, &context)
            .map_err(|e| format!("{}: {e:?}", case.name))?;
        let output_types = plan
            .output()
            .iter()
            .map(|f| spark_type(&f.ty))
            .collect::<Vec<_>>();
        let sql = SailSql {
            storage: &Storage,
            parameters: &params,
        }
        .emit(&plan)?;
        let optimized = JoinOptimizer {
            statistics: Some(&Stats),
            cost: &HashJoinCost,
            max_relations: 8,
        }
        .optimize(plan);
        let optimized_sql = SailSql {
            storage: &Storage,
            parameters: &params,
        }
        .emit(&optimized.logical)?;
        records.push(serde_json::json!({"name":case.name,"sql":sql,"optimized_sql":optimized_sql,"expected":case.expected,"ordered":case.ordered,"output_types":output_types,"trace":optimized.trace,"explain":if detailed_explain {Some(explain(&optimized))} else {None}}));
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

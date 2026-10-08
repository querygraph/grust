//! Typed result/program representation shared by qualification binaries.

pub fn spark_type(ty: &grust_lpg::LogicalType) -> String {
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

pub fn traversals(steps: &[grust_backend::query::program::TraversalStep]) -> serde_json::Value {
    serde_json::Value::Array(steps.iter().map(|s| serde_json::json!({"view":s.view,"seed_sql":s.seed_sql,"adjacency_sql":s.adjacency_sql,"min_hops":s.min_hops,"max_hops":s.max_hops,"mode":format!("{:?}",s.mode),"shortest_walk":s.shortest_walk})).collect())
}

pub fn execution_steps(
    steps: &[grust_backend::query::program::ExecutionStep],
) -> serde_json::Value {
    use grust_backend::query::program::ExecutionStep;
    serde_json::Value::Array(steps.iter().map(|step|match step {
        ExecutionStep::Materialize(s)=>serde_json::json!({"kind":"materialize","view":s.view,"sql":s.sql}),
        ExecutionStep::Traverse(s)=>serde_json::json!({"kind":"traverse","traversal":traversals(std::slice::from_ref(s))[0]}),
    }).collect())
}

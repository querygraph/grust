use grust_backend::query::SailSql;
use grust_optimizer::query::{explain, HashJoinCost, JoinOptimizer};
use grust_query_qualification::fixtures::*;
use grust_query_qualification::wire::{execution_steps, spark_type, traversals};
use grust_resolution::{query::QueryResolver, Context};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    if std::env::args().any(|arg| arg == "--cypher-refusals") {
        println!(
            "{}",
            serde_json::to_string_pretty(&grust_query_qualification::cypher_refusals::records()?)?
        );
        return Ok(());
    }
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
    let cypher = std::env::args().any(|arg| arg == "--cypher");
    let semantics = std::env::args().any(|arg| arg == "--semantics");
    let cases = if semantics {
        grust_query_qualification::semantics_cases::cases(&registry)?
    } else if cypher {
        grust_query_qualification::cypher_cases::cases(&registry)?
    } else if iterative {
        grust_query_qualification::iterative_cases::cases()
    } else {
        cases()
    };
    for case in cases {
        let plan = if iterative || cypher || semantics {
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
        records.push(serde_json::json!({"name":case.name,"expected_error":grust_query_qualification::semantics_cases::expected_error(case.name),"query_text":if semantics {grust_query_qualification::semantics_cases::source(case.name)} else if cypher {grust_query_qualification::cypher_cases::source(case.name)} else {None},"sql":program.sql,"optimized_sql":optimized_program.sql,"traversals":traversals(&program.traversals),"steps":execution_steps(&program.steps),"optimized_traversals":traversals(&optimized_program.traversals),"optimized_steps":execution_steps(&optimized_program.steps),"expected":case.expected,"ordered":case.ordered,"output_types":output_types,"trace":optimized.trace,"explain":if detailed_explain {Some(explain(&optimized))} else {None}}));
    }
    println!("{}", serde_json::to_string_pretty(&records)?);
    Ok(())
}

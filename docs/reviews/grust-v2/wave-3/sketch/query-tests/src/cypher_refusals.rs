//! Refusals stop at parse/lowering/resolution; no Sail server is involved.
use crate::fixtures::{registry, FixtureCatalog, Parameters, RelationPlugins};
use grust_cypher_frontend::{CypherLowering, CypherParser};
use grust_resolution::{query::QueryResolver, Context};
use grust_syntax::parse_and_lower;
use serde_json::{json, Value};
pub fn records() -> Result<Vec<Value>, String> {
    let registry = registry();
    let catalog = FixtureCatalog::default();
    let context = Context {
        catalog: &catalog,
        functions: &registry,
        parameters: &Parameters,
    };
    [
        ("empty_star", "RETURN *"),
        ("integer_division", "RETURN 5 / 2 AS x"),
        ("syntax","RETURN 'é' AS x; !"),
        ("multiple_statements","RETURN 1 AS x; RETURN 2 AS y"),
        ("missing_return","MATCH (n)"),
        ("write","CREATE (n) RETURN n"),
        ("call","CALL rows([1]) YIELD value RETURN value"),
        ("subquery","CALL { RETURN 1 AS x } RETURN x"),
        ("comma_paths","MATCH (a)-->(b), (c)-->(d) RETURN a"),
        ("path_value","MATCH p=(a)-[:KNOWS*]->(b) RETURN p"),
        ("edge_list","MATCH (a)-[r:KNOWS*1]->(b) RETURN r"),
        ("path_where","MATCH (a)-[:KNOWS*]->(b) WHERE b.id=1 RETURN b.id AS id"),
        ("with_order","UNWIND [2,1] AS x WITH x ORDER BY x RETURN x"),
        ("hidden_sort","MATCH (n:Person) RETURN n.id AS id ORDER BY n.age"),
        ("missing_alias","RETURN 1"),
        ("modulo","RETURN 5 % 2 AS x"),
        ("unknown_function","RETURN mystery(1) AS x"),
        ("wrong_function_type","RETURN upper(1) AS x"),
        ("unknown_graph","USE nowhere MATCH (n) RETURN n.id AS id"),
        ("unknown_label","MATCH (n:Unknown) RETURN n.id AS id"),
        ("unknown_property","MATCH (n:Person) RETURN n.missing AS value"),
        ("lost_scope","MATCH (n:Person) WITH n.name AS name RETURN n.id AS id"),
        ("predicate_type","MATCH (n:Person) WHERE 1 RETURN n.id AS id"),
        ("nested_aggregate","RETURN sum(count(*)) AS x"),
        ("unknown_parameter","RETURN $missing AS x"),
        ("negative_limit","RETURN 1 AS x LIMIT -1"),
    ].into_iter().map(|(name,source)| {
        match parse_and_lower(&CypherParser,&CypherLowering{functions:&registry},source) {
            Err(errors)=>Ok(json!({"name":name,"query_text":source,"outcome":"refused","stage":"frontend","diagnostics":errors.into_iter().map(|e|json!({"code":format!("{:?}",e.code),"message":e.message,"span":{"start":e.span.start,"end":e.span.end}})).collect::<Vec<_>>()})),
            Ok(plan)=>match QueryResolver.resolve_iterative(&plan,&context,&RelationPlugins) {
                Err(error)=>Ok(json!({"name":name,"query_text":source,"outcome":"refused","stage":"resolution","error":format!("{error:?}")})),
                Ok(_)=>Err(format!("refusal unexpectedly admitted: {name}: {source}")),
            }
        }
    }).collect()
}
#[cfg(test)]
mod tests {
    #[test]
    fn all_refusals_stop_before_engine_execution() {
        assert_eq!(super::records().unwrap().len(), 26);
    }
}

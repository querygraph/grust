//! Source-text cases and independent result bags for the native Sail gate.
use crate::fixtures::Case;
use grust_cypher_frontend::{CypherLowering, CypherParser};
use grust_functions::FunctionRegistry;
use grust_syntax::parse_and_lower;
use serde_json::{json, Value};
fn specifications() -> Vec<(&'static str, &'static str, Value, bool)> {
    vec![
        ("cypher_anonymous_scopes", "MATCH (:Person {id:1}) MATCH (:Person {id:2}) RETURN 1 AS x",json!([[1]]),false),
        ("cypher_shortest", "MATCH shortestPath((a:Person)-[:KNOWS*]->(b:Person)) RETURN a.id AS src,b.id AS dst",json!([[1,2],[1,3],[1,1],[2,3],[2,1],[2,2],[3,3],[3,1],[3,2]]),false),
        ("cypher_parameter", "MATCH (n:Person) WHERE n.age >= $minimum RETURN n.name AS name ORDER BY name",json!([["Alice"],["Dave"],["Eve"]]),true),
        ("cypher_optional_on", "MATCH (n:Person) OPTIONAL MATCH (n)-[:KNOWS]->(m:Person) WHERE m.age > 25 RETURN n.id AS id, m.id AS target ORDER BY id, target",json!([[1,null],[2,null],[3,1],[4,null],[5,null]]),true),
        ("cypher_multiset", "MATCH (a:Person)-[:KNOWS]->(b:Person) RETURN a.id AS src, b.id AS dst",json!([[1,2],[1,2],[2,3],[3,3],[3,1]]),false),
        ("cypher_distinct", "MATCH (a:Person)-[:KNOWS]->(b:Person) RETURN DISTINCT a.id AS src, b.id AS dst",json!([[1,2],[2,3],[3,3],[3,1]]),false),
        ("cypher_with", "MATCH (n:Person) WITH n.name AS name, n.age AS age WHERE age >= 30 RETURN name ORDER BY name SKIP 1 LIMIT 1",json!([["Dave"]]),true),
        ("cypher_aggregate_order", "MATCH (n:Person) RETURN count(*) AS total, n.age AS age ORDER BY age",json!([[1,20],[1,30],[1,35],[1,40],[1,null]]),true),
        ("cypher_count_optional", "OPTIONAL MATCH (n:Person {id: 99}) RETURN count(*) AS rows, count(n.id) AS present",json!([[1,0]]),false),
        ("cypher_unwind", "UNWIND [1,2,2,null] AS x RETURN x ORDER BY x DESC",json!([[null],[2],[2],[1]]),true),
        ("cypher_union", "RETURN 1 AS x UNION RETURN 1 AS x UNION ALL RETURN 1 AS x",json!([[1],[1]]),false),
        ("cypher_case", "MATCH (n:Person) RETURN CASE WHEN n.age IS NULL THEN 'unknown' ELSE n.name END AS name",json!([["Alice"],["Bob"],["unknown"],["Dave"],["Eve"]]),false),
        ("cypher_simple_case", "UNWIND [1,2] AS x RETURN CASE x WHEN 1 THEN 'one' ELSE 'other' END AS name",json!([["one"],["other"]]),false),
        ("cypher_quoted", "UNWIND [1] AS `odd name` RETURN `odd name` AS `result; --`",json!([[1]]),false),
        ("cypher_incoming", "MATCH (a:Person)<-[:KNOWS]-(b:Person) RETURN a.id AS dst,b.id AS src",json!([[2,1],[2,1],[3,2],[3,3],[1,3]]),false),
        ("cypher_trail", "MATCH (a:Person {id:3})-[:KNOWS]->(b)-[:KNOWS]->(c) RETURN b.id AS mid,c.id AS dst",json!([[3,1],[1,2],[1,2]]),false),
        ("cypher_star", "UNWIND [1,2] AS x WITH * RETURN *",json!([[1],[2]]),false),
        ("cypher_scalar", "MATCH (n:Person {id:1}) RETURN UPPER(n.name) AS name",json!([["ALICE"]]),false),
        ("cypher_bounded", "MATCH (a:Person {id:1})-[:KNOWS*1..2]->(b:Person) RETURN b.id AS target",json!([[2],[2],[3],[3]]),false),
        ("cypher_unbounded_chain", "USE chain MATCH (a:ChainNode {id:1})-[:CHAIN*]->(b:ChainNode {id:12}) RETURN b.id AS target",json!([[12]]),false),
    ]
}
pub fn source(name: &str) -> Option<&'static str> {
    specifications()
        .into_iter()
        .find(|(n, _, _, _)| *n == name)
        .map(|(_, s, _, _)| s)
}
pub fn cases(functions: &dyn FunctionRegistry) -> Result<Vec<Case>, String> {
    specifications()
        .into_iter()
        .map(|(name, source, expected, ordered)| {
            let plan = parse_and_lower(&CypherParser, &CypherLowering { functions }, source)
                .map_err(|e| format!("{name}: {e:?}"))?;
            Ok(Case {
                name,
                plan,
                expected,
                ordered,
            })
        })
        .collect()
}
#[cfg(test)]
mod tests {
    use super::*;
    use crate::fixtures::{registry, FixtureCatalog, Parameters, RelationPlugins};
    use grust_resolution::{query::QueryResolver, Context};
    #[test]
    fn source_queries_resolve_before_execution() {
        let functions = registry();
        let catalog = FixtureCatalog::default();
        let context = Context {
            catalog: &catalog,
            functions: &functions,
            parameters: &Parameters,
        };
        for case in cases(&functions).unwrap() {
            QueryResolver
                .resolve_iterative(&case.plan, &context, &RelationPlugins)
                .unwrap_or_else(|e| panic!("{}: {e:?}", case.name));
        }
    }
    #[test]
    fn aggregate_calls_use_registered_contracts() {
        let functions = registry();
        let plan = parse_and_lower(
            &CypherParser,
            &CypherLowering {
                functions: &functions,
            },
            "RETURN count(*) AS rows",
        )
        .unwrap();
        let grust_unresolved_plan::Relation::Project { input, .. } = plan.root else {
            panic!("project")
        };
        assert!(matches!(
            *input,
            grust_unresolved_plan::Relation::Aggregate { .. }
        ));
    }
    #[test]
    fn scalar_aggregate_name_collision_is_a_frontend_refusal() {
        use grust_functions::{FunctionKind, FunctionName};
        let mut functions = registry();
        let mut scalar =
            functions.lookup(&FunctionName::new("count"), FunctionKind::Aggregate)[0].clone();
        scalar.kind = FunctionKind::Scalar;
        functions.register(scalar).unwrap();
        let errors = parse_and_lower(
            &CypherParser,
            &CypherLowering {
                functions: &functions,
            },
            "RETURN count(1) AS x",
        )
        .unwrap_err();
        assert_eq!(
            errors[0].code,
            grust_syntax::DiagnosticCode::UnsupportedFeature
        );
        assert!(errors[0].message.contains("ambiguous"));
    }
}

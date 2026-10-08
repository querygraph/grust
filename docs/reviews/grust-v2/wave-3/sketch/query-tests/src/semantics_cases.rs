//! Exact bags for the semantics goal; keep failure and duplicate controls explicit.
use crate::fixtures::Case;
use grust_cypher_frontend::{CypherLowering, CypherParser};
use grust_functions::FunctionRegistry;
use grust_syntax::parse_and_lower;
use serde_json::{json, Value};
fn vertex(id: i64, name: &str, age: Value) -> Value {
    json!({"identity":id,"group":1,"graph":"fixture","kind":"vertex","labels":["Person"],"properties":{"age":age,"id":id,"name":name,"salary":null}})
}
fn edge(id: i64, src: i64, dst: i64) -> Value {
    json!({"identity":id,"group":10,"graph":"fixture","kind":"edge","labels":["KNOWS"],"properties":{"creationDate":id+1000,"source":id+2000},"source":src,"target":dst})
}
fn specifications() -> Vec<(&'static str, &'static str, Value, bool)> {
    vec![
        ("full_path_value","MATCH p=(a:Person {id:1})-[:KNOWS*1..1]->(b) RETURN p",json!([[{"length":1,"nodes":[vertex(1,"Alice",json!(30)),vertex(2,"Bob",json!(20))],"relationships":[edge(100,1,2)]}],[{"length":1,"nodes":[vertex(1,"Alice",json!(30)),vertex(2,"Bob",json!(20))],"relationships":[edge(101,1,2)]}]]),false),
        ("full_path_zero","MATCH p=(a:Person {id:4})-[:KNOWS*0..0]->(b) RETURN p",json!([[{"length":0,"nodes":[vertex(4,"Dave",json!(40))],"relationships":[]}]]),false),
        ("full_path_optional","MATCH (a:Person {id:4}) OPTIONAL MATCH p=(a)-[:KNOWS*1..1]->(b) RETURN p",json!([[null]]),false),
        ("full_fixed_path_scalar_edge","MATCH p=(a:Person {id:1})-[r:KNOWS]->(b) RETURN length(p) AS length,r AS relationship",json!([[1,{"identity":100,"group":10,"graph":"fixture","kind":"edge","properties":{"creationDate":1100,"source":2100}}],[1,{"identity":101,"group":10,"graph":"fixture","kind":"edge","properties":{"creationDate":1101,"source":2101}}]]),false),
        ("full_multi_fixed_path","MATCH p=(a:Person {id:1})-[:KNOWS]->(b)-[:KNOWS]->(c) UNWIND nodes(p) AS n RETURN n.id AS id ORDER BY id",json!([[1],[1],[2],[2],[3],[3]]),true),
        ("mixed_range_fixed_path","MATCH p=(a:Person {id:1})-[:KNOWS*1..2]->(b)-[:WORKS]->(c) RETURN length(p) AS length,c.id AS id",json!([[2,7],[2,7]]),false),
        ("mixed_explicit_one_edge_list","MATCH p=(a:Person {id:1})-[r:KNOWS*1]->(b)-[:WORKS]->(c) UNWIND r AS e RETURN length(p) AS length,e.identity AS id ORDER BY id",json!([[2,100],[2,101]]),true),
        ("mixed_segment_unique","MATCH p=(a:Person {id:3})-[:KNOWS*1]->(b)-[:KNOWS*1]->(c) RETURN b.id AS b,c.id AS c",json!([[3,1],[1,2],[1,2]]),false),
        ("path_length","MATCH p=(a:Person {id:1})-[:KNOWS*1..2]->(b) RETURN length(p) AS length ORDER BY length",json!([[1],[1],[2],[2]]),true),
        ("path_nodes_properties","MATCH p=(a:Person {id:1})-[:KNOWS*1..1]->(b) UNWIND nodes(p) AS n RETURN n.name AS name,n.id AS id,n.age AS age ORDER BY id",json!([["Alice",1,30],["Alice",1,30],["Bob",2,20],["Bob",2,20]]),true),
        ("path_edge_list","MATCH (a:Person {id:1})-[r:KNOWS*1..1]->(b) UNWIND r AS e RETURN e.identity AS id,e.source AS src,e.target AS dst ORDER BY id",json!([[100,2100,2],[101,2101,2]]),true),
        ("path_edge_properties","MATCH (a:Person {id:1})-[r:KNOWS*1]->(b) UNWIND r AS e RETURN e.creationDate AS date,e.source AS source ORDER BY date",json!([[1100,2100],[1101,2101]]),true),
        ("path_reverse_edges","MATCH p=(a:Person {id:2})<-[:KNOWS*1..1]-(b) UNWIND relationships(p) AS e RETURN e.identity AS id,e.source AS src,e.target AS dst ORDER BY id",json!([[100,2100,2],[101,2101,2]]),true),
        ("path_zero_hop_lists","MATCH p=(a:Person {id:4})-[:KNOWS*0..0]->(b) RETURN length(p) AS hops,relationships(p) AS edges",json!([[0,[]]]),false),
        ("path_optional_null","MATCH (a:Person {id:4}) OPTIONAL MATCH p=(a)-[:KNOWS*1..1]->(b) RETURN length(p) AS hops,nodes(p) AS nodes,relationships(p) AS edges",json!([[null,null,null]]),false),
        ("union_hidden_order_columns","UNWIND [2,1] AS x RETURN x+10 AS n ORDER BY x UNION ALL RETURN 13 AS n",json!([[11],[12],[13]]),false),
        ("correlated_union_order_columns","UNWIND [1,2] AS x CALL { UNWIND [2,1] AS y RETURN y+x AS n ORDER BY y UNION ALL RETURN x AS n } RETURN x,n",json!([[1,2],[1,3],[1,1],[2,3],[2,4],[2,2]]),false),
        ("with_order_dropped_key","UNWIND [3,1,2] AS x WITH x AS age, x+10 AS name ORDER BY age RETURN name",json!([[11],[12],[13]]),true),
        ("with_order_two_projections","UNWIND [3,1,2] AS x WITH x AS age, x+10 AS name ORDER BY age WITH name RETURN name",json!([[11],[12],[13]]),true),
        ("with_filter_before_limit","UNWIND [3,1,2] AS x WITH x ORDER BY x LIMIT 1 WHERE x>1 RETURN x",json!([[2]]),true),
        ("return_hidden_sort","UNWIND [3,1,2] AS x RETURN x+10 AS name ORDER BY x",json!([[11],[12],[13]]),true),
        ("return_alias_expression_sort","UNWIND [3,1,2] AS x RETURN x AS name ORDER BY -name",json!([[3],[2],[1]]),true),
        ("distinct_drops_prior_sort_key","UNWIND [3,1,2] AS x WITH x ORDER BY x RETURN DISTINCT 1 AS n",json!([[1]]),false),
        ("with_order_limit","UNWIND [3,1,2] AS x WITH x ORDER BY x DESC RETURN x LIMIT 2",json!([[3],[2]]),true),
        ("numeric_exact_large_integer","WITH 9007199254740993 AS n,9007199254740992.0 AS f RETURN n=f AS equal,n>f AS greater,f<n AS reverse",json!([[false,true,true]]),false),
        ("numeric_mixed_fraction","WITH 7 AS n,7.5 AS f RETURN n<f AS lower,n=f AS equal,n>f AS upper",json!([[true,false,false]]),false),
        ("numeric_max_boundary","WITH 9223372036854775807 AS n,9223372036854775808.0 AS f RETURN n<f AS lower,n=f AS equal,n/1 AS exact",json!([[true,false,9223372036854775807i64]]),false),
        ("numeric_min_division","WITH -9223372036854775807-1 AS n RETURN n/-1 AS divide,n%-1 AS modulo",json!([[-9223372036854775808i64,0]]),false),
        ("numeric_float_zero","RETURN (1.0/0.0)>0 AS positive,(1.0/-0.0)<0 AS negative,(0.0/0.0)=0.0 AS nanEqual",json!([[true,true,false]]),false),
        ("numeric_null_zero","WITH null AS n RETURN n/0 AS value",json!([[null]]),false),
        ("numeric_branch_not_evaluated","WITH 9223372036854775807 AS n RETURN CASE WHEN false THEN n+1 ELSE 1 END AS value",json!([[1]]),false),
        ("numeric_divide_zero_error","UNWIND [0] AS d RETURN 1/d AS value",json!([]),false),
        ("numeric_mixed_divide_zero_error","UNWIND [0] AS d RETURN 1.0/d AS value",json!([]),false),
        ("numeric_overflow_error","WITH 9223372036854775807 AS n RETURN n+1 AS value",json!([]),false),
        ("numeric_multiply_overflow_error","WITH 9223372036854775807 AS n RETURN n*n AS value",json!([]),false),
        ("numeric_integer_division","WITH 7 AS n RETURN n/2 AS positive, -n/2 AS negative, n%2 AS remainder",json!([[3,-3,1]]),false),
        ("numeric_mixed","WITH 7 AS n,2.0 AS d RETURN n/d AS fraction,n+d AS sum,n=d AS equal",json!([[3.5,9.0,false]]),false),
        ("numeric_null","WITH null AS n RETURN n/2 AS value",json!([[null]]),false),

        ("call_correlated_bag","UNWIND [1,1,2] AS x CALL rows([x,x+1]) YIELD value AS y RETURN x,y",json!([[1,1],[1,2],[1,1],[1,2],[2,2],[2,3]]),false),
        ("call_where_outer","UNWIND [1,2] AS x CALL rows([1,2,3]) YIELD value AS y WHERE y > x RETURN x,y",json!([[1,2],[1,3],[2,3]]),false),
        ("call_empty","UNWIND [1,2] AS x CALL rows([]) YIELD value AS y RETURN x",json!([]),false),
        ("subquery_scalar_bag","UNWIND [1,1,2] AS x CALL { RETURN x+1 AS y } RETURN x,y",json!([[1,2],[1,2],[2,3]]),false),
        ("subquery_global_count","UNWIND [1,1,4] AS x CALL { MATCH (n:Person {id:x})-[:KNOWS]->(m) RETURN count(*) AS count } RETURN x,count",json!([[1,2],[1,2],[4,0]]),false),
        ("subquery_global_sum","UNWIND [1,4] AS x CALL { MATCH (n:Person {id:x})-[:KNOWS]->(m) RETURN sum(m.age) AS age } RETURN x,age",json!([[1,40],[4,null]]),false),
        ("subquery_top_one","UNWIND [1,2,3] AS x CALL { UNWIND [1,2,3] AS y WITH y WHERE y >= x RETURN y ORDER BY y DESC LIMIT 1 } RETURN x,y",json!([[1,3],[2,3],[3,3]]),false),
        ("subquery_union_per_row","UNWIND [1,1,2] AS x CALL { RETURN x AS y UNION RETURN x AS y } RETURN x,y",json!([[1,1],[1,1],[2,2]]),false),
        ("subquery_nested","UNWIND [1,1,2] AS x CALL { CALL { RETURN x+1 AS z } RETURN z+1 AS y } RETURN x,y",json!([[1,3],[1,3],[2,4]]),false),

        ("match_wide_unique","MATCH (a:Person {id:3})-[:KNOWS]->(b), (a)-[:KNOWS]->(c) RETURN b.id AS b,c.id AS c",json!([[3,1],[1,3]]),false),
        ("match_parallel_unique","MATCH (a:Person {id:1})-[:KNOWS]->(b), (a)-[:KNOWS]->(c) RETURN b.id AS b,c.id AS c",json!([[2,2],[2,2]]),false),
        ("match_ranges_unique","MATCH (a:Person {id:3})-[:KNOWS]->(b), (a)-[:KNOWS*1..1]->(c) RETURN b.id AS b,c.id AS c",json!([[3,1],[1,3]]),false),
        ("match_repeated_range_empty","MATCH (a:Person {id:1})-[r:KNOWS*1]->(b), (a)-[r:KNOWS*1]->(c) RETURN b.id AS b,c.id AS c",json!([]),false),
        ("match_repeated_zero_range","MATCH (a:Person {id:4})-[r:KNOWS*0..0]->(b), (a)-[r:KNOWS*0..0]->(c) RETURN b.id AS b,c.id AS c",json!([[4,4]]),false),
        ("match_repeated_edge_empty","MATCH (a:Person)-[r:KNOWS]->(b), (a)-[r:KNOWS]->(c) RETURN b.id AS b,c.id AS c",json!([]),false),
        ("match_zero_edge_sets","MATCH (a:Person {id:3})-[:KNOWS*0..0]->(b), (a)-[:KNOWS*0..0]->(c) RETURN b.id AS b,c.id AS c",json!([[3,3]]),false),
        ("separate_match_can_reuse","MATCH (a:Person {id:3})-[:KNOWS]->(b) MATCH (a)-[:KNOWS]->(c) RETURN b.id AS b,c.id AS c",json!([[3,3],[3,1],[1,3],[1,1]]),false),
        ("optional_comma_preserves_row","MATCH (a:Person {id:4}) OPTIONAL MATCH (a)-[:KNOWS]->(b), (a)-[:KNOWS]->(c) RETURN a.id AS a,b.id AS b,c.id AS c",json!([[4,null,null]]),false),
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

pub fn expected_error(name: &str) -> Option<&'static str> {
    match name {
        "numeric_divide_zero_error" | "numeric_mixed_divide_zero_error" => {
            Some("grust numeric integer division by zero")
        }
        "numeric_overflow_error" | "numeric_multiply_overflow_error" => {
            Some("grust numeric integer overflow")
        }
        _ => None,
    }
}

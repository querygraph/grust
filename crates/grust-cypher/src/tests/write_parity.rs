//! Differential parity between the legacy string-scanning write planner and
//! the AST write planner.
//!
//! Two checks run while both planners exist:
//!
//! - Every call of the public write entry points made by this crate's unit
//!   tests also runs the other planner with the same options
//!   ([`assert_plan_parity`], [`assert_return_parity`]).
//! - [`write_planner_parity_over_collected_statements`] runs both planners,
//!   under several option sets, on every string literal in the workspace's
//!   Rust sources that mentions a write keyword, and on the statements in this
//!   crate's JSON corpora.
//!
//! Plans and bindings must be identical (generated node ids are compared by
//! position, since each run draws fresh UUIDs); errors must have the same
//! `GrustError` variant. A difference is a test failure unless
//! [`known_difference`] lists it with its justification.

use super::*;
use std::sync::Mutex;

/// A planner outcome in comparable form: the plan and bindings rendered with
/// generated ids replaced by their position, or the error's variant and
/// message.
#[derive(Clone, Debug, PartialEq)]
enum Outcome {
    Planned(String),
    Failed(&'static str, String),
}

fn error_class(error: &GrustError) -> &'static str {
    match error {
        GrustError::Backend(_) => "Backend",
        GrustError::Schema(_) => "Schema",
        GrustError::Unsupported(_) => "Unsupported",
        GrustError::CypherSyntax(_) => "CypherSyntax",
        GrustError::CypherUnresolvedIdentity(_) => "CypherUnresolvedIdentity",
        GrustError::CypherUnsupportedCardinality(_) => "CypherUnsupportedCardinality",
        GrustError::CypherExecution(_) => "CypherExecution",
        GrustError::Serialization(_) => "Serialization",
        GrustError::ResourceLimitExceeded { .. } => "ResourceLimitExceeded",
        GrustError::GraphExpectationFailed(_) => "GraphExpectationFailed",
        GrustError::GraphIdempotencyConflict(_) => "GraphIdempotencyConflict",
    }
}

fn normalize_generated(mut text: String, generated: &[CypherGeneratedNodeId]) -> String {
    for (index, generated) in generated.iter().enumerate() {
        text = text.replace(generated.id.as_str(), &format!("node-generated-{index}"));
    }
    text
}

fn sorted<V: std::fmt::Debug>(map: &HashMap<String, V>) -> BTreeMap<&str, String> {
    map.iter()
        .map(|(key, value)| (key.as_str(), format!("{value:?}")))
        .collect()
}

type PlanResult = Result<(GraphMutationPlan, Vec<CypherGeneratedNodeId>)>;

fn plan_outcome(result: &PlanResult) -> Outcome {
    match result {
        Ok((plan, generated)) => Outcome::Planned(normalize_generated(
            format!("{plan:?} {generated:?}"),
            generated,
        )),
        Err(error) => Outcome::Failed(error_class(error), error.to_string()),
    }
}

fn return_outcome(result: &Result<CypherPlannedMutationWithReturn>) -> Outcome {
    match result {
        Ok(planned) => Outcome::Planned(normalize_generated(
            format!(
                "{:?} {:?} {:?} {:?} {:?} {:?} {:?} {:?} {:?}",
                planned.plan,
                planned.generated_node_ids,
                sorted(&planned.node_bindings),
                sorted(&planned.edge_bindings),
                sorted(&planned.row_node_bindings),
                sorted(&planned.row_edge_match_bindings),
                sorted(&planned.row_edge_bindings),
                sorted(&planned.row_path_bindings),
                planned.return_clause,
            ),
            &planned.generated_node_ids,
        )),
        Err(error) => Outcome::Failed(error_class(error), error.to_string()),
    }
}

/// How two outcomes compare.
#[derive(Clone, Copy, Debug, PartialEq)]
enum Verdict {
    /// Identical plans and bindings, or identical errors.
    Equal,
    /// Both failed with the same error variant and different messages.
    SameClassNewMessage,
    /// Anything else.
    Different,
}

fn verdict(legacy: &Outcome, ast: &Outcome) -> Verdict {
    match (legacy, ast) {
        (left, right) if left == right => Verdict::Equal,
        (Outcome::Failed(left, _), Outcome::Failed(right, _)) if left == right => {
            Verdict::SameClassNewMessage
        }
        _ => Verdict::Different,
    }
}

/// Differences between the planners that are intended, with the reason.
/// Each entry is matched against the statement text exactly.
fn known_difference(cypher: &str) -> Option<&'static str> {
    KNOWN_DIFFERENCES
        .iter()
        .find(|(statement, _)| *statement == cypher)
        .map(|(_, reason)| *reason)
}

/// Id strings from the test suites, not statements. The string planner
/// required whitespace after a leading keyword and called these unsupported
/// statements (`CypherSyntax`); the parser reads `delete-a` as `DELETE -a`,
/// whose target is not a node pattern (`Unsupported`, as `DELETE -a` with a
/// space always was).
const HYPHENATED_DELETE: &str = "parsed as DELETE with a negated target";

const BACKTICK_VARIABLE: &str = "a backtick-quoted variable is the name it quotes; the string planner rejected `n` as a variable name";
const VARIABLE_LENGTH: &str = "the string planner stored `R*2` as the relationship type; variable-length patterns are now rejected";
const TYPE_ALTERNATIVES: &str =
    "the string planner stored `R|S` as one relationship type; alternative types are now rejected";
const MULTIPLE_LABELS: &str = "the string planner stored and matched `A:B` as one label; patterns with several labels are now rejected";
const STRING_ARITHMETIC: &str = "the string planner stored the text between the outer quotes, `x' + 'y`; an operator expression is not a literal and is now rejected";
const LITERAL_SPELLING: &str = "the parser reads `- 5`, `1e3`, `True` and `Null` as the literals they are; the string planner rejected these spellings";
const KEYWORD_ADJACENCY: &str = "a keyword followed directly by `(` is a keyword; the string planner required whitespace after it";
const KEYWORD_SPACING: &str = "the parser reads keywords independent of spacing; the string planner required exactly one space in `STARTS WITH` and spaces around `AND`";
const UNICODE_ESCAPE: &str = "the parser decodes `\\u0041` as `A`; the string planner kept `u0041`";

const KNOWN_DIFFERENCES: &[(&str, &str)] = &[
    ("delete-a", HYPHENATED_DELETE),
    ("delete-b", HYPHENATED_DELETE),
    ("delete-mixed-a", HYPHENATED_DELETE),
    ("delete-mixed-b", HYPHENATED_DELETE),
    ("delete-resolved-edge", HYPHENATED_DELETE),
    ("delete-resolved-node", HYPHENATED_DELETE),
    ("delete-row-a", HYPHENATED_DELETE),
    ("delete-row-b", HYPHENATED_DELETE),
    ("delete-row-c", HYPHENATED_DELETE),
    ("CREATE (`n`:X {id: 'a'})", BACKTICK_VARIABLE),
    (
        "CREATE (a {id: 'a'})-[:R*2]->(b {id: 'b'})",
        VARIABLE_LENGTH,
    ),
    (
        "CREATE (a {id: 'a'})-[:R|S]->(b {id: 'b'})",
        TYPE_ALTERNATIVES,
    ),
    ("CREATE (n:A:B {id: 'a'})", MULTIPLE_LABELS),
    ("MATCH (n:A:B {id: 'a'}) SET n.x = 1", MULTIPLE_LABELS),
    ("MATCH (n:A:B) DELETE n", MULTIPLE_LABELS),
    ("CREATE (n:X {id: 'a', v: 'x' + 'y'})", STRING_ARITHMETIC),
    ("CREATE (n:X {id: 'a', v: - 5})", LITERAL_SPELLING),
    ("CREATE (n:X {id: 'a', v: 1e3})", LITERAL_SPELLING),
    ("CREATE (n:X {id: 'a', v: True})", LITERAL_SPELLING),
    ("CREATE (n:X {id: 'a', v: Null})", LITERAL_SPELLING),
    ("CREATE (n:X {id: 'a'})RETURN n", KEYWORD_ADJACENCY),
    ("CREATE(n:X {id: 'a'})", KEYWORD_ADJACENCY),
    ("MERGE(n:X {id: 'a'})", KEYWORD_ADJACENCY),
    ("MATCH(n:X {id: 'a'}) DELETE n", KEYWORD_ADJACENCY),
    ("DELETE(n)", KEYWORD_ADJACENCY),
    (
        "MATCH (n:X) WHERE n.name STARTS  WITH 'a' SET n.y = 1",
        KEYWORD_SPACING,
    ),
    (
        "MATCH (n:X) WHERE n.x=1 AND(n.y=2) SET n.z = 3",
        KEYWORD_SPACING,
    ),
    (
        "MATCH (n:X) WHERE n.v = 'a\\u0041' DELETE n",
        UNICODE_ESCAPE,
    ),
];

fn report_difference(entry: &str, cypher: &str, legacy: &Outcome, ast: &Outcome) -> String {
    format!("{entry}: {cypher:?}\n  legacy: {legacy:?}\n  ast:    {ast:?}")
}

/// Called by `cypher_mutation_plan_with_options` under `cfg(test)` with the
/// AST planner's result.
pub(crate) fn assert_plan_parity(cypher: &str, options: &CypherMutationOptions, ast: &PlanResult) {
    let legacy = legacy_mutation_plan_with_options(cypher, options.clone());
    let (legacy, ast) = (plan_outcome(&legacy), plan_outcome(ast));
    if verdict(&legacy, &ast) == Verdict::Different && known_difference(cypher).is_none() {
        panic!(
            "write planner parity\n{}",
            report_difference("plan", cypher, &legacy, &ast)
        );
    }
}

/// Called by `cypher_mutation_plan_with_return_options` under `cfg(test)`
/// with the AST planner's result.
pub(crate) fn assert_return_parity(
    cypher: &str,
    options: &CypherMutationOptions,
    ast: &Result<CypherPlannedMutationWithReturn>,
) {
    let legacy = legacy_mutation_plan_with_return_options(cypher, options.clone());
    let (legacy, ast) = (return_outcome(&legacy), return_outcome(ast));
    if verdict(&legacy, &ast) == Verdict::Different && known_difference(cypher).is_none() {
        panic!(
            "write planner parity\n{}",
            report_difference("return", cypher, &legacy, &ast)
        );
    }
}

// ---------------------------------------------------------------------------
// Corpus collection
// ---------------------------------------------------------------------------

/// The string literals of a Rust source file, unescaped. Comments, char
/// literals and lifetimes are skipped; byte strings are ignored.
fn rust_string_literals(source: &str) -> Vec<String> {
    let chars: Vec<char> = source.chars().collect();
    let mut literals = Vec::new();
    let mut index = 0;
    while index < chars.len() {
        let ch = chars[index];
        let next = chars.get(index + 1).copied();
        if ch == '/' && next == Some('/') {
            while index < chars.len() && chars[index] != '\n' {
                index += 1;
            }
            continue;
        }
        if ch == '/' && next == Some('*') {
            index += 2;
            while index + 1 < chars.len() && !(chars[index] == '*' && chars[index + 1] == '/') {
                index += 1;
            }
            index += 2;
            continue;
        }
        if ch == '\'' {
            // A char literal, or a lifetime.
            if next == Some('\\') {
                index += 2;
                while index < chars.len() && chars[index] != '\'' {
                    index += 1;
                }
                index += 1;
            } else if chars.get(index + 2) == Some(&'\'') {
                index += 3;
            } else {
                index += 1;
            }
            continue;
        }
        let previous_is_ident = index > 0 && {
            let previous = chars[index - 1];
            previous.is_alphanumeric() || previous == '_'
        };
        if ch == 'r' && !previous_is_ident && matches!(next, Some('"' | '#')) {
            let mut hashes = 0;
            let mut cursor = index + 1;
            while chars.get(cursor) == Some(&'#') {
                hashes += 1;
                cursor += 1;
            }
            if chars.get(cursor) == Some(&'"') {
                let start = cursor + 1;
                let mut end = start;
                'raw: while end < chars.len() {
                    if chars[end] == '"'
                        && (0..hashes).all(|h| chars.get(end + 1 + h) == Some(&'#'))
                    {
                        break 'raw;
                    }
                    end += 1;
                }
                literals.push(chars[start..end.min(chars.len())].iter().collect());
                index = end + 1 + hashes;
                continue;
            }
        }
        if ch == 'b' && !previous_is_ident && next == Some('"') {
            index += 2;
            while index < chars.len() && chars[index] != '"' {
                if chars[index] == '\\' {
                    index += 1;
                }
                index += 1;
            }
            index += 1;
            continue;
        }
        if ch == '"' {
            let mut value = String::new();
            index += 1;
            while index < chars.len() && chars[index] != '"' {
                if chars[index] == '\\' {
                    index += 1;
                    match chars.get(index) {
                        Some('n') => value.push('\n'),
                        Some('t') => value.push('\t'),
                        Some('r') => value.push('\r'),
                        Some('0') => value.push('\0'),
                        Some('\n') => {
                            while chars.get(index + 1).is_some_and(|c| c.is_whitespace()) {
                                index += 1;
                            }
                        }
                        Some('u') => {
                            let open = index + 2;
                            let close = (open..chars.len()).find(|&i| chars[i] == '}');
                            if let Some(close) = close {
                                let hex: String = chars[open..close].iter().collect();
                                if let Some(decoded) =
                                    u32::from_str_radix(&hex, 16).ok().and_then(char::from_u32)
                                {
                                    value.push(decoded);
                                }
                                index = close;
                            }
                        }
                        Some(other) => value.push(*other),
                        None => {}
                    }
                    index += 1;
                    continue;
                }
                value.push(chars[index]);
                index += 1;
            }
            literals.push(value);
            index += 1;
            continue;
        }
        index += 1;
    }
    literals
}

fn mentions_write_keyword(text: &str) -> bool {
    let upper = text.to_ascii_uppercase();
    ["CREATE", "MERGE", "DELETE", "SET", "REMOVE"]
        .iter()
        .any(|keyword| upper.contains(keyword))
}

fn collect_rust_files(dir: &std::path::Path, out: &mut Vec<std::path::PathBuf>) {
    let Ok(entries) = std::fs::read_dir(dir) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        let name = entry.file_name();
        if name == "target" || name.to_string_lossy().starts_with('.') {
            continue;
        }
        if path.is_dir() {
            collect_rust_files(&path, out);
        } else if path.extension().is_some_and(|ext| ext == "rs") {
            out.push(path);
        }
    }
}

fn json_strings(value: &serde_json::Value, out: &mut Vec<String>) {
    match value {
        serde_json::Value::String(text) => out.push(text.clone()),
        serde_json::Value::Array(items) => items.iter().for_each(|item| json_strings(item, out)),
        serde_json::Value::Object(map) => map.values().for_each(|item| json_strings(item, out)),
        _ => {}
    }
}

/// Every candidate write statement: workspace Rust string literals and this
/// crate's JSON corpora, deduplicated, in a stable order.
fn collect_statements() -> Vec<String> {
    let crate_dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR"));
    let workspace_crates = crate_dir.parent().expect("crates directory");
    let mut files = Vec::new();
    collect_rust_files(workspace_crates, &mut files);
    files.sort();
    let mut statements = BTreeSet::new();
    for file in &files {
        let Ok(source) = std::fs::read_to_string(file) else {
            continue;
        };
        for literal in rust_string_literals(&source) {
            if literal.len() < 20_000 && mentions_write_keyword(&literal) {
                statements.insert(literal);
            }
        }
    }
    for corpus in [
        "tests/golden/write_golden.json",
        "tests/golden/write_corpus.json",
        "tests/gql/strict_write.json",
        "tests/gql/portable_read.json",
    ] {
        let text = std::fs::read_to_string(crate_dir.join(corpus)).expect("corpus file");
        let value: serde_json::Value = serde_json::from_str(&text).expect("corpus JSON");
        let mut strings = Vec::new();
        json_strings(&value, &mut strings);
        statements.extend(
            strings
                .into_iter()
                .filter(|text| mentions_write_keyword(text)),
        );
    }
    statements.extend(ADVERSARIAL.iter().map(|statement| statement.to_string()));
    statements.into_iter().collect()
}

/// Edge cases of the string planner's text handling: unusual spacing,
/// quoting, literals, pattern shapes, and clauses it does not support.
const ADVERSARIAL: &[&str] = &[
    // Literals.
    "CREATE (n:X {id: 'a', v: -5, w: +5, f: -1.5, g: .5, h: 1., t: true, u: TRUE, z: null})",
    "CREATE (n:X {id: 'a', v: 1e3})",
    "CREATE (n:X {id: 'a', v: True})",
    "CREATE (n:X {id: 'a', v: Null})",
    "CREATE (n:X {id: 'a', v: [1, 2]})",
    "CREATE (n:X {id: 'a', v: {k: 1}})",
    "CREATE (n:X {id: 'a', v: 'x' + 'y'})",
    "CREATE (n:X {id: 'a', v: 1 + 2})",
    "CREATE (n:X {id: 'a', v: - 5})",
    "CREATE (n:X {id: 'a', v: --5})",
    "CREATE (n:X {id: 'a', v: 'it\\'s'})",
    "CREATE (n:X {id: 'a', v: 'tab\\tnew\\nline'})",
    "CREATE (n:X {id: 'a', v: \"double\"})",
    "CREATE (n:X {id: 'a', v: $p})",
    "CREATE (n:X {id: 'a', v: $0})",
    "CREATE (n:X {id: 5})",
    "CREATE (n:X {'id': 'a', `odd key`: 1, order: 2})",
    "CREATE (n:X {id: 'a', id: 'b'})",
    "CREATE (n:X)",
    "CREATE (:X {name: 'no id'})",
    "CREATE ({id: 'a'})",
    // Names.
    "CREATE (`n`:X {id: 'a'})",
    "CREATE (`my n`:X {id: 'a'})",
    "CREATE (n:`X Y` {id: 'a'})",
    "CREATE (n: X {id: 'a'})",
    "CREATE (n:A:B {id: 'a'})",
    "MATCH (n:A:B) DELETE n",
    "MATCH (n:A:B {id: 'a'}) SET n.x = 1",
    // Spacing and keyword adjacency.
    "CREATE(n:X {id: 'a'})",
    "MERGE(n:X {id: 'a'})",
    "MATCH(n:X {id: 'a'}) DELETE n",
    "DELETE(n)",
    "create (n:X {id: 'a'})",
    "CREATE  (n:X {id: 'a'})",
    "MATCH (n:X) WHERE n.name STARTS  WITH 'a' SET n.y = 1",
    "MATCH (n:X) WHERE n.x=1 AND(n.y=2) SET n.z = 3",
    "MATCH (n:X) WHERE n.x = 1 XOR n.y = 2 SET n.z = 3",
    // Edge patterns.
    "CREATE (a {id: 'a'})-[:R]->(b {id: 'b'})",
    "CREATE (a {id: 'a'})<-[:R]-(b {id: 'b'})",
    "CREATE (a {id: 'a'})-[:R]-(b {id: 'b'})",
    "CREATE (a {id: 'a'})-->(b {id: 'b'})",
    "CREATE (a {id: 'a'})-[]->(b {id: 'b'})",
    "CREATE (a {id: 'a'})-[r]->(b {id: 'b'})",
    "CREATE (a {id: 'a'})-[:R|S]->(b {id: 'b'})",
    "CREATE (a {id: 'a'})-[:R*2]->(b {id: 'b'})",
    "CREATE (a {id: 'a'})-[:R]->(b {id: 'b'})-[:S]->(c {id: 'c'})",
    "CREATE (a {id: 'a'}), (b {id: 'b'})",
    "CREATE (a {id: 'a'}), (a)-[:R]->(b {id: 'b'})",
    "CREATE p = (a {id: 'a'})-[:R]->(b {id: 'b'})",
    "CREATE (a:X {id: 'a'})-[:R {id: 'e1', w: 2}]->(b:Y {id: 'b'})",
    "CREATE (a {id: 'a'})-[:R {id: 5}]->(b {id: 'b'})",
    "CREATE (a)-[:R]->(b)",
    "CREATE (a:X {id: 'a'}); CREATE (b:X {id: 'b'}); CREATE (a)-[r:R]->(b)",
    "CREATE (a:X {id: 'a'}); CREATE (a)-[r:R]->(:Y {id: 'b'}); CREATE (a)-[r:R]->(:Y {id: 'c'})",
    // Bare DELETE.
    "CREATE (n:X {id: 'a'}); DELETE (n)",
    "CREATE (n:X {id: 'a'}); DELETE n",
    "CREATE (n:X {id: 'a'}); DELETE ((n))",
    "CREATE (n:X {id: 'a'}); DELETE (n), (n)",
    "CREATE (n:X {id: 'a'}); DETACH DELETE (n)",
    "DELETE (m)",
    "DELETE (n.x)",
    // MATCH DELETE.
    "MATCH (n:X {id: 'a'}) DETACH DELETE n",
    "MATCH (n:X) WHERE n.v = 1 DETACH DELETE n",
    "MATCH (n:X) WHERE n.v IS NULL DETACH DELETE n",
    "MATCH (n:X) WHERE n.v IN [1] DETACH DELETE n",
    "MATCH (n:X) WHERE n.v = $p DETACH DELETE n",
    "MATCH (a)-[r:R]->(b) DETACH DELETE r",
    "MATCH (a)-[r:R]->(b) WHERE r.w > 1 DETACH DELETE r",
    "MATCH (n:X) DELETE n RETURN n",
    "MATCH (n:X) DELETE n, n",
    "MATCH (n:X) DELETE n.x",
    "MATCH (n:X), (m:Y) DELETE n",
    "MATCH (n:X), (m:Y) WHERE m.v = 1 DELETE n",
    "MATCH (n:X) WITH n DELETE n",
    "MATCH (n:X) WHERE n.v = 1 WITH n DELETE n",
    "MATCH (n:X) SET n.v = 1 DELETE n",
    "MATCH p = (n:X) DELETE n",
    "MATCH p = (a)-[r:R]->(b) DELETE r",
    "MATCH p = (a)-[r:R]->(b) DELETE a",
    "MATCH (a), p = (b)-[r:R]->(c) DELETE r",
    "MATCH (a)-[r:R]-(b) DELETE r",
    "MATCH (a)-[r:R]-(b) WHERE r.w = 1 DELETE r",
    "MATCH (a)-->(b) DELETE a",
    "MATCH (a)-[r:R]->(b)-[s:S]->(c) DELETE r",
    "MATCH (c), (a)-[r:R]->(b) DELETE r",
    "MATCH (a {id: 'a'})-[r:R]->(b {id: 'b'}) DELETE r, a, b",
    "MATCH (a)-[r:R]->(b) DELETE z",
    "MATCH (a)-[:R]->(b) DELETE a",
    "MATCH shortestPath((a)-[r:R]->(b)) DELETE r",
    "OPTIONAL MATCH (n:X) DELETE n",
    // MATCH CREATE / MERGE.
    "MATCH (a:X {id: 'a'}), (b:X {id: 'b'}) CREATE (a)-[:R]->(b), (b)-[:S]->(a)",
    "MATCH (a:X), (b:X) CREATE (a)-[:R]->(b), (b)-[:S]->(a)",
    "MATCH (a:X), (b:X) CREATE p = (a)-[r:R]->(b)",
    "MATCH (a:X), (b:X) CREATE p = (a)-[:R]->(b)",
    "MATCH (a:X), (b:X) CREATE p = (a)-[r:R]->(b), (b)-[:S]->(a)",
    "MATCH (a:X), (b:X) CREATE (a)-[r:R]->(b) SET r.x = 1",
    "MATCH (a:X), (b:X) CREATE (a)-[r:R]->(b) RETURN r",
    "MATCH (a:X), (b:X) CREATE (a)-[r:R]->(b) RETURN r.x = 1",
    "MATCH (a:X), (b:X) MERGE (a)-[r:R]->(b) ON CREATE SET r.x = 1",
    "MATCH (a:X), (b:X) MERGE (a)-[r:R]->(b) ON MATCH SET r.x = 1",
    "MATCH (a:X), (b:X) CREATE (c:X {id: 'c'})",
    "MATCH (a:X), (a:Y) CREATE (a)-[:R]->(a)",
    "MATCH (a:X), (:Y) CREATE (a)-[:R]->(a)",
    "MATCH (a:X)-[:R]->(b) CREATE (a)-[:S]->(b)",
    "MATCH p = (a:X) CREATE (a)-[:S]->(a)",
    "MATCH (a:X), (b:X) CREATE (a:X)-[:S]->(b)",
    "MATCH (a:X), (b:X) CREATE (a)-[:S]->(c)",
    "MATCH (a:X), (b:X) WHERE a.v > 1 AND b.w = 'q' CREATE (a)-[:S {k: 1}]->(b)",
    "MATCH (a:X), (b:X) WHERE c.v > 1 CREATE (a)-[:S]->(b)",
    "MATCH (a:X), (b:X) CREATE (a)-[:S {id: 7}]->(b)",
    "MATCH (a:X), (b:X) CREATE (a)<-[:S]-(b)",
    "MATCH (a:X), (b:X) CREATE (a)-[:S]-(b)",
    "MATCH (a:X), (b:X) WITH a, b CREATE (a)-[:S]->(b)",
    // MATCH SET.
    "MATCH (n:X) SET n.v = n.v + 1",
    "MATCH (n:X) SET n.v = n.v - -1",
    "MATCH (n:X) SET n.v = n.v * 2 + 1",
    "MATCH (n:X) SET n.v = n.v + 1 * 2",
    "MATCH (n:X) SET n.v = 2 * n.v",
    "MATCH (n:X) SET n.v = n.w",
    "MATCH (n:X) SET n.v = n.w % 2",
    "MATCH (n:X) SET n.v = n.w + 'a'",
    "MATCH (n:X) SET n.v = n.w + $p",
    "MATCH (n:X) SET n.v = n.a.b + 1",
    "MATCH (n:X) SET n.a.b = 1",
    "MATCH (n:X) SET n.v = null",
    "MATCH (n:X) SET n += {a: 1, b: 'x'}",
    "MATCH (n:X) SET n += $props",
    "MATCH (n:X) SET n += {a: 1} RETURN n",
    "MATCH (n:X) SET n = {a: 1}",
    "MATCH (n:X) SET n:Y",
    "MATCH (n:X) SET n:Y, n.v = 1",
    "MATCH (n:X) SET n.v = 1, n:Y",
    "MATCH (n:X) SET n.v = 1 RETURN n",
    "MATCH (n:X) SET n.v = $p RETURN n",
    "MATCH (n:X) SET n.v = 'a' RETURN n.v",
    "MATCH (n:X) SET n.v = n.v + 1 RETURN n",
    "MATCH (n:X) SET n.v = 1 SET n.w = 2",
    "MATCH (n:X) SET n.v = 1 REMOVE n.w",
    "MATCH (n:X) SET m.v = 1",
    "MATCH (n:X {id: 'a'}) SET n.v = 1, n.w = 2",
    "MATCH (a:X), (b:Y) SET a.v = b.w + 1",
    "MATCH (a:X), (b:Y) WHERE a.k = 1 AND b.k = 2 SET a.v = b.w * 2",
    "MATCH (a:X), (b:Y) SET a.v = c.w + 1",
    "MATCH (a:X)-[:R]->(b:Y) SET a.v = b.w + 1",
    "MATCH (a:X)<-[:R]-(b:Y) SET a.v = b.w + 1",
    "MATCH (a:X)-[r:R]->(b:Y) SET r.v = b.w + 1",
    "MATCH (a:X)-[:R {k: 1}]->(b:Y) SET a.v = b.w + 1",
    "MATCH p = (a:X)-[:R]->(b:Y) SET a.v = b.w + 1",
    "MATCH (a:X), (b:Y), (c:Z) SET a.v = b.w + 1",
    "MATCH (a:X) SET a.v = b.w + 1",
    "MATCH (a:X)-[r:R]->(b) SET r.w = 1",
    "MATCH (a {id: 'a'})-[r:R]->(b {id: 'b'}) SET r.w = 1",
    "MATCH (a {id: 'a'})-[r:R]->(b {id: 'b'}) SET r.w = r.w + 1",
    "MATCH (a {id: 'a'})-[r:R]->(b {id: 'b'}) SET r.w = null",
    "MATCH (a)-[r:R]->(b) SET r += {w: 1}",
    "MATCH (a)-[r:R]->(b) SET a.w = 1",
    "MATCH (a)-[:R]->(b) SET a.w = 1",
    "MATCH p = (a)-[r:R]->(b) SET r.w = 1",
    "MATCH p = (n:X) SET n.v = 1",
    "MATCH (n:X) WHERE n.v = 1 WITH n SET n.w = 2",
    "MATCH (n:X) WITH n SET n.w = 2",
    "MATCH (n:X) WITH n WHERE n.v = 1 SET n.w = 2",
    // MATCH REMOVE.
    "MATCH (n:X) REMOVE n.v",
    "MATCH (n:X) REMOVE n.v, n.w",
    "MATCH (n:X) REMOVE n:Y",
    "MATCH (n:X) REMOVE n:Y, n.v",
    "MATCH (n:X) REMOVE n.v RETURN n",
    "MATCH (n:X) REMOVE n:Y RETURN n",
    "MATCH (n:X) REMOVE n:Y RETURN n.v",
    "MATCH (n:X) REMOVE n.a.b",
    "MATCH (n:X) REMOVE m.v",
    "MATCH (n:X {id: 'a'}) REMOVE n.v",
    "MATCH (a)-[r:R]->(b) REMOVE r.v",
    "MATCH (a {id: 'a'})-[r:R]->(b {id: 'b'}) REMOVE r.v",
    "MATCH (a)-[r:R]->(b) REMOVE a.v",
    "MATCH p = (a)-[r:R]->(b) REMOVE r.v",
    "MATCH (n:X) WITH n REMOVE n.v",
    // WHERE leaves.
    "MATCH (n:X) WHERE n.v = 1 OR n.v = 2 DELETE n",
    "MATCH (n:X) WHERE NOT (n.v = 1 OR n.v = 2) DELETE n",
    "MATCH (n:X) WHERE NOT NOT n.v = 1 DELETE n",
    "MATCH (n:X) WHERE NOT n.v IS NULL DELETE n",
    "MATCH (n:X) WHERE n.v IS NOT NULL AND n.w <> 'a' DELETE n",
    "MATCH (n:X) WHERE n.v != 2 DELETE n",
    "MATCH (n:X) WHERE n.v >= 1 AND n.v <= 9 DELETE n",
    "MATCH (n:X) WHERE n.v > true DELETE n",
    "MATCH (n:X) WHERE n.v STARTS WITH 1 DELETE n",
    "MATCH (n:X) WHERE n.v ENDS WITH 'a' OR n.v ENDS WITH 'b' DELETE n",
    "MATCH (n:X) WHERE n.v CONTAINS $p DELETE n",
    "MATCH (n:X) WHERE n.v IN [] DELETE n",
    "MATCH (n:X) WHERE n.v IN [1, 'a', true, 1.5] DELETE n",
    "MATCH (n:X) WHERE n.v IN [null] DELETE n",
    "MATCH (n:X) WHERE n.v IN [[1]] DELETE n",
    "MATCH (n:X) WHERE n.v IN $p DELETE n",
    "MATCH (n:X) WHERE n.v IN 5 DELETE n",
    "MATCH (n:X) WHERE NOT n.v IN [1, 2] DELETE n",
    "MATCH (n:X) WHERE 1 = n.v DELETE n",
    "MATCH (n:X) WHERE n.v = n.w DELETE n",
    "MATCH (n:X) WHERE n.v + 1 > 2 DELETE n",
    "MATCH (n:X) WHERE size(n.v) > 2 DELETE n",
    "MATCH (n:X) WHERE n.a.b = 1 DELETE n",
    "MATCH (n:X) WHERE n DELETE n",
    "MATCH (n:X) WHERE NOT n.v DELETE n",
    "MATCH (n:X) WHERE m.v = 1 DELETE n",
    "MATCH (n:X) WHERE n.v = 1 AND (n.w = 2 OR n.w = 3) DELETE n",
    "MATCH (n:X) WHERE (n.v = 1 AND n.w = 2) OR n.w = 3 DELETE n",
    "MATCH (n:X) WHERE n.v = 1.5e2 DELETE n",
    "MATCH (n:X) WHERE n.`odd key` = 1 DELETE n",
    "MATCH (n:X) WHERE n.v = 'a\\u0041' DELETE n",
    // Statement level.
    "MATCH (n:X) RETURN n",
    "MATCH (n:X) DELETE n UNION MATCH (m:X) DELETE m",
    "UNWIND [1, 2] AS x CREATE (n:X {id: 'a'})",
    "WITH 1 AS x CREATE (n:X {id: 'a'})",
    "CREATE (n:X {id: 'a'}) SET n.v = 1",
    "CREATE (n:X {id: 'a'}) REMOVE n.v",
    "CREATE (n:X {id: 'a'}) CREATE (m:X {id: 'b'})",
    "CREATE (n:X {id: 'a'}) DELETE n",
    "CREATE (n:X {id: 'a'}) MERGE (a {id: 'a'})-[:R]->(b {id: 'b'})",
    "MERGE (n:X {id: 'a'}) ON CREATE SET n.v = 1",
    "CREATE (n:X {id: 'a'}) RETURN n",
    "CREATE (n:X {id: 'a'})RETURN n",
    "CREATE (n:X {id: 'a', return: 1}) RETURN n",
    "CREATE (n:X {id: 'a', `return`: 1}) RETURN n.return",
    "CREATE (n:X {id: 'a'}) RETURN",
    "RETURN 1",
    "CREATE (n:X {id: 'a'}) RETURN n; CREATE (m:X {id: 'b'}) RETURN m",
    "CREATE (a:X {id: 'a'})-[r:R]->(b:X {id: 'b'}) RETURN r",
    "MATCH (n:X {id: 'a'}) DELETE n RETURN n",
    "MATCH (n:X) DELETE n RETURN count(n)",
    "MATCH (a)-[r:R]->(b) DELETE r RETURN r",
    "MATCH (a)-[r:R]->(b) DELETE a RETURN a",
    "MATCH (n:X {id: 'a'}) SET n.v = 1 RETURN n.v",
    "MATCH (n:X) SET n.v = 1 RETURN n.v ORDER BY n.v LIMIT 2",
    "MATCH (a:X), (b:X) CREATE p = (a)-[r:R]->(b) RETURN p",
    "MATCH (a:X), (b:X) MERGE (a)-[r:R]->(b) RETURN r, a, b",
    "MATCH (n:X) REMOVE n.v RETURN n",
    "MATCH p = (a)-[r:R]->(b) DELETE r RETURN p",
    "CREATE (n:X {id: 'a'}); MATCH (n) SET n.v = 1 RETURN n",
    "CREATE (n:X {id: 'a'}); MATCH (n:X) SET n.v = 1 RETURN n",
    "MATCH (n:X) DELETE n; MATCH (n:X) DELETE n",
    "MATCH (n:X) SET n.v = 1; MATCH (n:Y) SET n.v = 1",
    "CREATE (a:X {id: 'a'})-[r:R]->(b:X {id: 'b'}); MATCH (a)-[r:R]->(b) DELETE r",
    "CREATE (a:X {id: 'a'})-[r:R]->(b:X {id: 'b'}); MATCH (a)-[r:S]->(b) DELETE r",
    "CREATE (n:X {id: 'a'}); CREATE (n:X {id: 'b'})",
    "CREATE (n:X {id: 'a'}); MATCH (n:X {id: 'b'}) DELETE n",
    "",
    ";",
    "  ;  ; ",
    "// only a comment",
    "CREATE (n:X {id: 'a'}) /* note */ RETURN n",
    "CREATE (n:X {id: 'a;b'}); CREATE (m:X {id: 'c'})",
    "CREATE (n:X {id: 'unterminated})",
    "CREATE (n:X {id: 'a'}) /* unterminated",
];

/// The parameter names a statement mentions, read with the lexer.
fn parameter_names(statement: &str) -> BTreeSet<String> {
    let (tokens, _) = crate::lexer::tokenize_prefix(statement);
    tokens
        .into_iter()
        .filter_map(|token| match token.token {
            crate::lexer::Token::Parameter(name) => Some(name),
            _ => None,
        })
        .collect()
}

/// The option sets each statement is planned under.
fn option_variants(statement: &str) -> Vec<(String, CypherMutationOptions)> {
    let policies = [
        ("default", CypherMutationOptions::default()),
        (
            "generate-node-ids",
            CypherMutationOptions {
                node_id_policy: CypherNodeIdPolicy::GenerateForCreate,
                ..CypherMutationOptions::default()
            },
        ),
        (
            "row-create-ids",
            CypherMutationOptions {
                relationship_id_policy: CypherRelationshipIdPolicy::GenerateForRowCreate,
                ..CypherMutationOptions::default()
            },
        ),
        (
            "row-create-merge-ids",
            CypherMutationOptions {
                relationship_id_policy: CypherRelationshipIdPolicy::GenerateForRowCreateAndMerge,
                ..CypherMutationOptions::default()
            },
        ),
        (
            "null-removes",
            CypherMutationOptions {
                null_assignment: CypherNullAssignment::RemoveProperty,
                ..CypherMutationOptions::default()
            },
        ),
    ];
    let names = parameter_names(statement);
    let mut parameter_sets = vec![("no-params", CypherParameters::new())];
    if !names.is_empty() {
        for (label, value) in [
            ("string-params", Value::from("v")),
            ("int-params", Value::Int(7)),
            ("list-params", Value::IntArray(vec![1, 2])),
        ] {
            parameter_sets.push((
                label,
                names
                    .iter()
                    .map(|name| (name.clone(), value.clone()))
                    .collect(),
            ));
        }
    }
    let mut variants = Vec::new();
    for (policy, options) in &policies {
        for (label, parameters) in &parameter_sets {
            variants.push((
                format!("{policy}/{label}"),
                CypherMutationOptions {
                    parameters: parameters.clone(),
                    ..options.clone()
                },
            ));
        }
    }
    variants
}

#[derive(Default)]
struct Tally {
    statements: usize,
    comparisons: usize,
    equal: usize,
    planned_equal: usize,
    message_changes: Vec<String>,
    known: Vec<String>,
    differences: Vec<String>,
}

static LAST_TALLY: Mutex<Option<String>> = Mutex::new(None);

#[test]
fn write_planner_parity_over_collected_statements() {
    let statements = collect_statements();
    let mut tally = Tally {
        statements: statements.len(),
        ..Tally::default()
    };
    for statement in &statements {
        for (variant, options) in option_variants(statement) {
            let pairs = [
                (
                    "plan",
                    plan_outcome(&legacy_mutation_plan_with_options(
                        statement,
                        options.clone(),
                    )),
                    plan_outcome(&crate::write_ast::ast_mutation_plan_with_options(
                        statement,
                        options.clone(),
                    )),
                ),
                (
                    "return",
                    return_outcome(&legacy_mutation_plan_with_return_options(
                        statement,
                        options.clone(),
                    )),
                    return_outcome(&crate::write_ast::ast_mutation_plan_with_return_options(
                        statement,
                        options.clone(),
                    )),
                ),
            ];
            for (entry, legacy, ast) in pairs {
                tally.comparisons += 1;
                let label = format!("{entry} [{variant}]");
                match verdict(&legacy, &ast) {
                    Verdict::Equal => {
                        tally.equal += 1;
                        if matches!(legacy, Outcome::Planned(_)) {
                            tally.planned_equal += 1;
                        }
                    }
                    Verdict::SameClassNewMessage => {
                        tally.equal += 1;
                        if variant == "default/no-params" {
                            tally
                                .message_changes
                                .push(report_difference(&label, statement, &legacy, &ast));
                        }
                    }
                    Verdict::Different => {
                        let report = report_difference(&label, statement, &legacy, &ast);
                        if let Some(reason) = known_difference(statement) {
                            tally.known.push(format!("{report}\n  reason: {reason}"));
                        } else {
                            tally.differences.push(report);
                        }
                    }
                }
            }
        }
    }
    let summary = format!(
        "write planner parity: {} statements, {} comparisons, {} equal ({} planned identically, {} same error class with a new message under default options), {} known differences, {} unexplained differences",
        tally.statements,
        tally.comparisons,
        tally.equal,
        tally.planned_equal,
        tally.message_changes.len(),
        tally.known.len(),
        tally.differences.len()
    );
    println!("{summary}");
    if std::env::var_os("GRUST_WRITE_PARITY_VERBOSE").is_some() {
        for change in &tally.message_changes {
            println!("message change: {change}");
        }
        for known in &tally.known {
            println!("known difference: {known}");
        }
    }
    *LAST_TALLY.lock().expect("tally lock") = Some(summary.clone());
    assert!(
        tally.differences.is_empty(),
        "{summary}\n\n{}",
        tally.differences.join("\n\n")
    );
}

/// Mutations of each single statement that add text the planner does not
/// support in the places the string planner was most sensitive to: after the
/// statement, before the write clause, and after `MATCH`.
fn mutations(statement: &str) -> Vec<String> {
    let statement = statement.trim();
    if statement.contains(';') || statement.is_empty() {
        return Vec::new();
    }
    let mut out = vec![
        format!("{statement} RETURN n"),
        format!("{statement} RETURN n.v"),
        format!("{statement} RETURN n.v = 1, m"),
        format!("{statement} UNION MATCH (m) DELETE m"),
        format!("{statement} SET z.q = 1"),
        format!("{statement} WITH n"),
        format!("{statement}, (extra)"),
    ];
    let upper = statement.to_ascii_uppercase();
    for keyword in [
        " DELETE ", " SET ", " REMOVE ", " CREATE ", " MERGE ", " WHERE ",
    ] {
        if let Some(index) = upper.find(keyword) {
            let (head, rest) = statement.split_at(index);
            out.push(format!("{head} WITH n{rest}"));
            out.push(format!("{head} WITH n WHERE n.k = 1{rest}"));
            out.push(format!("{head} DETACH{rest}"));
            out.push(format!("{head}, (extra){rest}"));
            out.push(format!("{head}, p = (q)-[:R]->(s){rest}"));
        }
    }
    out
}

#[test]
#[ignore = "exploratory: mutations of the corpus; run with --ignored"]
fn write_planner_parity_over_mutations() {
    let mut differences = BTreeMap::new();
    let mut comparisons = 0usize;
    for statement in collect_statements() {
        if known_difference(&statement).is_some() {
            continue;
        }
        for mutated in mutations(&statement) {
            let options = CypherMutationOptions::default();
            let pairs = [
                (
                    "plan",
                    plan_outcome(&legacy_mutation_plan_with_options(
                        &mutated,
                        options.clone(),
                    )),
                    plan_outcome(&crate::write_ast::ast_mutation_plan_with_options(
                        &mutated,
                        options.clone(),
                    )),
                ),
                (
                    "return",
                    return_outcome(&legacy_mutation_plan_with_return_options(
                        &mutated,
                        options.clone(),
                    )),
                    return_outcome(&crate::write_ast::ast_mutation_plan_with_return_options(
                        &mutated,
                        options.clone(),
                    )),
                ),
            ];
            for (entry, legacy, ast) in pairs {
                comparisons += 1;
                if verdict(&legacy, &ast) == Verdict::Different {
                    differences
                        .entry(mutated.clone())
                        .or_insert_with(|| report_difference(entry, &mutated, &legacy, &ast));
                }
            }
        }
    }
    println!(
        "mutation parity: {comparisons} comparisons, {} statements differ",
        differences.len()
    );
    for report in differences.values() {
        println!("{report}\n");
    }
}

#[test]
fn rust_literal_extraction_unescapes_and_skips_comments() {
    let source = r##"
        // "not a literal"
        let a = "CREATE (n:A {id: 'x'})";
        let b = r#"MATCH (n) SET n.x = "q""#;
        let c = 'x'; fn f<'a>(s: &'a str) {}
        let d = "line \
                 continued\n";
    "##;
    assert_eq!(
        rust_string_literals(source),
        vec![
            "CREATE (n:A {id: 'x'})".to_string(),
            "MATCH (n) SET n.x = \"q\"".to_string(),
            "line continued\n".to_string(),
        ]
    );
}

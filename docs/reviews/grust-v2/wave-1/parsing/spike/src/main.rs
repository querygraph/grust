//! Parsing spike for the Grust v2 parsing report.
//!
//! Usage: parsing-spike <agree|errors|bench|corpus|probes>
//!
//! The ten subset queries are copied verbatim from grust-cypher v0.24.0 tests;
//! the source of each is noted beside it.

use subset_chumsky as alt_chumsky;
use subset_winnow as alt_winnow;

use std::hint::black_box;
use std::time::Instant;

const QUERIES: [&str; 10] = [
    // tests/gql/portable_read.json
    "MATCH (n:Person) RETURN n.name",
    "MATCH (n:Person {name: 'Ada'}) WHERE n.age >= 18 RETURN n.name",
    "MATCH (a:Person) OPTIONAL MATCH (a)-[:KNOWS]->(b) RETURN a.name, b.name",
    "MATCH (a:Person {name:'Ada'})-[:KNOWS*1..2]->(b) RETURN b.name",
    "MATCH (n) RETURN n.label AS label, count(*) AS c",
    "MATCH (n) RETURN DISTINCT n.label AS l ORDER BY l",
    "MATCH p = (:Person)-[:KNOWS]->(:Person) RETURN length(p)",
    // benches/cypher_pipeline.rs SEGMENT_READ
    "MATCH (a:Person)-[:KNOWS]->()-[:KNOWS]->(c:Person) WHERE a.age >= 21 AND c.active = true RETURN a.name, c.name",
    // src/tests (predicates, returning)
    "MATCH (n:Person) WHERE NOT n.name IN ['Ada', 'Alan'] RETURN n",
    "MATCH (n:Person) WHERE n.age >= 40 RETURN n.name ORDER BY n.age DESC SKIP 1 LIMIT 2",
];

const MALFORMED: [(&str, &str); 4] = [
    ("E1 missing ')'", "MATCH (n:Person RETURN n.name"),
    ("E2 missing operand", "MATCH (a)-[:KNOWS]->(b) WHERE a.age > RETURN b.name"),
    ("E3 misspelled keyword", "MATCH (n:Person) RETRUN n.name"),
    ("E4 two errors", "MATCH (a:Person {name: })-[:KNOWS]->(b) WHERE b.age > (3 + ) RETURN b"),
];

/// GQL (ISO/IEC 39075) and newer Cypher syntax, to see what today's parser accepts.
const PROBES: [(&str, &str); 24] = [
    ("GQL quantified edge {m,n}", "MATCH (a)-[:KNOWS]->{1,3}(b) RETURN b"),
    ("GQL/Cypher25 parenthesized QPP", "MATCH ((a)-[:KNOWS]->(b)){1,3} RETURN b"),
    ("GQL quantifier +", "MATCH (a)-[:KNOWS]->+(b) RETURN b"),
    ("GQL label disjunction", "MATCH (n:Person|Robot) RETURN n"),
    ("GQL label conjunction/negation", "MATCH (n:Person&!Robot) RETURN n"),
    ("GQL IS label", "MATCH (n IS Person) RETURN n"),
    ("GQL element WHERE", "MATCH (n:Person WHERE n.age > 30) RETURN n"),
    ("GQL abbreviated edge ->", "MATCH (a)->(b) RETURN b"),
    ("GQL path search ANY SHORTEST", "MATCH ANY SHORTEST (a)-[:KNOWS]->*(b) RETURN b"),
    ("GQL path mode TRAIL", "MATCH TRAIL (a)-[:KNOWS]->*(b) RETURN b"),
    ("GQL match mode", "MATCH DIFFERENT EDGES (a)-[e]->(b) RETURN e"),
    ("GQL graph pattern YIELD", "MATCH (a)-[e]->(b) YIELD a, b RETURN a"),
    ("GQL INSERT", "INSERT (:Person {name: 'Ada'})"),
    ("GQL FILTER and LET", "MATCH (n:Person) FILTER n.age > 30 LET x = n.age RETURN x"),
    ("GQL NEXT", "MATCH (n) RETURN n NEXT MATCH (m) RETURN m"),
    ("GQL OFFSET", "MATCH (n) RETURN n OFFSET 1 LIMIT 2"),
    ("GQL graph type DDL", "CREATE GRAPH TYPE t AS { (:Person {name STRING}) }"),
    ("Cypher UNWIND", "UNWIND [1, 2] AS x RETURN x"),
    ("Cypher EXISTS subquery", "MATCH (n) WHERE EXISTS { (n)-[:KNOWS]->() } RETURN n"),
    ("Cypher COUNT subquery", "MATCH (n) RETURN COUNT { (n)-[:KNOWS]->() } AS c"),
    ("Cypher map projection", "MATCH (n) RETURN n {.name, .age}"),
    ("Cypher list slice", "RETURN [1, 2, 3][0..2] AS xs"),
    ("Cypher pattern comprehension", "MATCH (n) RETURN [(n)-[:KNOWS]->(m) | m.name] AS xs"),
    ("Cypher FOREACH", "MATCH (n) FOREACH (x IN [1] | SET n.v = x)"),
];

fn caret(source: &str, start: usize, end: usize) -> String {
    let start = start.min(source.len());
    let width = end.saturating_sub(start).max(1);
    format!("    {source}\n    {}{}", " ".repeat(start), "^".repeat(width))
}

fn today(q: &str) -> Result<(), (usize, usize, String)> {
    grust_cypher::parser::parse_query(q)
        .map(|_| ())
        .map_err(|e| (e.span.start, e.span.end, e.render(q)))
}

fn agree() {
    let mut ok = true;
    for q in QUERIES {
        let w = alt_winnow::parse(q);
        let c = alt_chumsky::parse(q);
        let t = today(q);
        let same = matches!((&w, &c), (Ok(a), Ok(b)) if a == b);
        println!("today={} winnow={} chumsky={} same_ast={} | {q}", t.is_ok(), w.is_ok(), c.is_ok(), same);
        if !same {
            println!("  winnow:  {w:?}\n  chumsky: {c:?}");
        }
        ok &= same && t.is_ok();
    }
    println!("ALL_AGREE={ok}");
    if let Ok(q) = alt_winnow::parse(QUERIES[7]) {
        println!("sample AST (query 8, winnow): {q:?}");
    }
}

fn errors() {
    for (label, q) in MALFORMED {
        println!("=== {label}\n    {q}");
        match today(q) {
            Ok(()) => println!("-- today: ACCEPTED"),
            Err((s, e, m)) => println!("-- today (1 error):\n{}\n    {m}", caret(q, s, e)),
        }
        match alt_winnow::parse(q) {
            Ok(_) => println!("-- winnow: ACCEPTED"),
            Err((off, m)) => {
                println!("-- winnow (1 error):\n{}\n    {}", caret(q, off, off + 1), m.replace('\n', " | "))
            }
        }
        match alt_chumsky::parse(q) {
            Ok(_) => println!("-- chumsky: ACCEPTED"),
            Err(es) => {
                println!("-- chumsky ({} error(s)):", es.len());
                for (s, e, m) in es {
                    println!("{}\n    {m}", caret(q, s, e));
                }
            }
        }
        println!();
    }
}

fn time_ns_per_query(f: &dyn Fn(&str) -> bool, iters: usize) -> (f64, f64) {
    for q in QUERIES {
        assert!(f(q), "warm-up parse failed: {q}");
    }
    let mut rounds = Vec::new();
    for _ in 0..9 {
        let t = Instant::now();
        for _ in 0..iters {
            for q in QUERIES {
                black_box(f(black_box(q)));
            }
        }
        rounds.push(t.elapsed().as_nanos() as f64 / (iters * QUERIES.len()) as f64);
    }
    rounds.sort_by(|a, b| a.partial_cmp(b).unwrap());
    (rounds[4], rounds[0])
}

fn bench() {
    let iters = 20_000;
    let total_bytes: usize = QUERIES.iter().map(|q| q.len()).sum();
    println!("10 queries, {total_bytes} bytes total, mean {} bytes/query; {iters} iterations x 9 rounds", total_bytes / 10);
    let lex: &dyn Fn(&str) -> bool = &|q| grust_cypher::lexer::tokenize(q).is_ok();
    let t: &dyn Fn(&str) -> bool = &|q| grust_cypher::parser::parse_query(q).is_ok();
    let w: &dyn Fn(&str) -> bool = &|q| alt_winnow::parse(q).is_ok();
    let c: &dyn Fn(&str) -> bool = &|q| alt_chumsky::parse(q).is_ok();
    for (name, f) in [
        ("grust lexer only (tokenize)", lex),
        ("today: grust parse_query (lex+parse, full grammar)", t),
        ("winnow subset (char-level, no lexer)", w),
        ("chumsky subset (grust lexer + chumsky)", c),
    ] {
        let (median, min) = time_ns_per_query(f, iters);
        println!("{name:55} median {median:8.0} ns/query  min {min:8.0} ns/query");
    }
}

fn corpus() {
    let root = "/Users/alexy/src/grust-f1/crates/grust-cypher/tests";
    let mut stmts: Vec<String> = Vec::new();
    for f in ["gql/portable_read.json", "gql/strict_write.json"] {
        let v: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(format!("{root}/{f}")).unwrap()).unwrap();
        for c in v["cases"].as_array().unwrap() {
            stmts.push(c["statement"].as_str().unwrap().to_string());
        }
    }
    let v: serde_json::Value =
        serde_json::from_str(&std::fs::read_to_string(format!("{root}/golden/write_corpus.json")).unwrap()).unwrap();
    for s in v.as_array().unwrap() {
        stmts.push(s.as_str().unwrap().to_string());
    }
    let accepted: Vec<&String> = stmts.iter().filter(|s| grust_cypher::parser::parse_statements(s).is_ok()).collect();
    let bytes: usize = accepted.iter().map(|s| s.len()).sum();
    println!("corpus: {} sources ({} accepted by parse_statements, {} rejected at parse level), {} bytes accepted", stmts.len(), accepted.len(), stmts.len() - accepted.len(), bytes);
    for s in &stmts {
        if let Err(e) = grust_cypher::parser::parse_statements(s) {
            println!("  rejected: {} | {}", s.split_whitespace().collect::<Vec<_>>().join(" "), e.message);
        }
    }
    let iters = 2_000;
    let mut rounds = Vec::new();
    for _ in 0..9 {
        let t = Instant::now();
        for _ in 0..iters {
            for s in &accepted {
                black_box(grust_cypher::parser::parse_statements(black_box(s)).is_ok());
            }
        }
        let e = t.elapsed().as_secs_f64();
        rounds.push(e);
    }
    rounds.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let med = rounds[4];
    println!(
        "today parse_statements over accepted corpus: median {:.0} ns/source, {:.1} MB/s",
        med * 1e9 / (iters * accepted.len()) as f64,
        (bytes * iters) as f64 / med / 1e6
    );
}

fn probes() {
    println!("--- today's typed parser (grust_cypher::parser::parse_query) on GQL / newer Cypher syntax");
    for (label, q) in PROBES {
        match today(q) {
            Ok(()) => println!("ACCEPT | {label:34} | {q}"),
            Err((_, _, m)) => println!("REJECT | {label:34} | {q}\n       |   {m}"),
        }
    }
    println!("\n--- legacy string-scanning write path vs typed parser");
    let opts = grust_cypher::CypherMutationOptions::default;
    for (label, q) in [
        ("';' inside a backtick label", "CREATE (n:`A;B` {id: 'x'})"),
        ("keyword inside a backtick property name", "MATCH (n:Person {id: 'p1'}) SET n.`x CREATE y` = 1"),
        ("control: same statement, plain name", "MATCH (n:Person {id: 'p1'}) SET n.x = 1"),
    ] {
        let typed = grust_cypher::parser::parse_query(q).map(|_| ()).map_err(|e| e.render(q));
        let legacy = grust_cypher::cypher_mutation_plan_with_options(q, opts()).map(|(p, _)| p.operations.len());
        println!("{label}\n    {q}\n    typed parser: {typed:?}\n    write planner: {legacy:?}");
    }
    println!("\n--- DDL goes to the string-scanning path, not the typed parser");
    for q in ["CREATE CONSTRAINT FOR (n:Person) REQUIRE n.id IS UNIQUE", "CREATE GRAPH TYPE g AS NODE Person (name STRING)"] {
        let typed = grust_cypher::parser::parse_query(q).map(|_| ()).map_err(|e| e.render(q));
        let ddl = grust_cypher::cypher_ddl(q).map(|v| v.len());
        println!("    {q}\n    typed parser: {typed:?}\n    cypher_ddl:   {ddl:?}");
    }
}

fn main() {
    match std::env::args().nth(1).as_deref() {
        Some("agree") => agree(),
        Some("errors") => errors(),
        Some("bench") => bench(),
        Some("corpus") => corpus(),
        Some("probes") => probes(),
        _ => eprintln!("usage: parsing-spike <agree|errors|bench|corpus|probes>"),
    }
}

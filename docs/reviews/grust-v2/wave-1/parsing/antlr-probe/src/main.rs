//! ANTLR 4 Rust target probe: grammars-v4 Cypher grammar and opengql GQL grammar,
//! generated with the antlr4rust v0.6.0 tool jar, runtime antlr4rust 0.6.0.
#![allow(warnings)]
use antlr4rust::common_token_stream::CommonTokenStream;
use antlr4rust::error_listener::ErrorListener;
use antlr4rust::errors::ANTLRError;
use antlr4rust::recognizer::Recognizer;
use antlr4rust::token_factory::TokenFactory;
use antlr4rust::InputStream;
use std::cell::RefCell;
use std::hint::black_box;
use std::rc::Rc;
use std::time::Instant;

#[cfg(feature = "cypher")]
#[path = "cypher"]
mod cypher {
    pub mod cypherlexer;
    pub mod cypherparser;
    pub mod cypherparserlistener;
    pub mod cypherparservisitor;
}
#[cfg(feature = "gql")]
#[path = "gql"]
mod gql {
    pub mod gqllexer;
    pub mod gqlparser;
    pub mod gqllistener;
    pub mod gqlvisitor;
}

#[derive(Clone, Default)]
struct Collect(Rc<RefCell<Vec<String>>>);
impl<'a, T: Recognizer<'a>> ErrorListener<'a, T> for Collect {
    fn syntax_error(&self, _r: &T, _s: Option<&<T::TF as TokenFactory<'a>>::Inner>, line: isize, col: isize, msg: &str, _e: Option<&ANTLRError>) {
        self.0.borrow_mut().push(format!("line {line}:{col} {msg}"));
    }
}

macro_rules! parse_fn {
    ($name:ident, $m:ident, $lexer:ident, $lexmod:ident, $parser:ident, $parsemod:ident, $rule:ident) => {
        fn $name(q: &str) -> Vec<String> {
            let errs = Collect::default();
            let mut lexer = $m::$lexmod::$lexer::new(InputStream::new(q));
            lexer.remove_error_listeners();
            lexer.add_error_listener(Box::new(errs.clone()));
            let mut parser = $m::$parsemod::$parser::new(CommonTokenStream::new(lexer));
            use antlr4rust::parser::Parser;
            parser.remove_error_listeners();
            parser.add_error_listener(Box::new(errs.clone()));
            let tree = parser.$rule();
            black_box(&tree);
            let v = errs.0.borrow().clone();
            v
        }
    };
}
#[cfg(feature = "cypher")]
parse_fn!(parse_cypher, cypher, CypherLexer, cypherlexer, CypherParser, cypherparser, script);
#[cfg(feature = "gql")]
parse_fn!(parse_gql, gql, GQLLexer, gqllexer, GQLParser, gqlparser, gqlProgram);

const CYPHER: [&str; 10] = [
    "MATCH (n:Person) RETURN n.name",
    "MATCH (n:Person {name: 'Ada'}) WHERE n.age >= 18 RETURN n.name",
    "MATCH (a:Person) OPTIONAL MATCH (a)-[:KNOWS]->(b) RETURN a.name, b.name",
    "MATCH (a:Person {name:'Ada'})-[:KNOWS*1..2]->(b) RETURN b.name",
    "MATCH (n) RETURN n.label AS label, count(*) AS c",
    "MATCH (n) RETURN DISTINCT n.label AS l ORDER BY l",
    "MATCH p = (:Person)-[:KNOWS]->(:Person) RETURN length(p)",
    "MATCH (a:Person)-[:KNOWS]->()-[:KNOWS]->(c:Person) WHERE a.age >= 21 AND c.active = true RETURN a.name, c.name",
    "MATCH (n:Person) WHERE NOT n.name IN ['Ada', 'Alan'] RETURN n",
    "MATCH (n:Person) WHERE n.age >= 40 RETURN n.name ORDER BY n.age DESC SKIP 1 LIMIT 2",
];
// The same ten queries in ISO GQL spelling where the spelling differs.
const GQL: [&str; 10] = [
    "MATCH (n:Person) RETURN n.name",
    "MATCH (n:Person {name: 'Ada'}) WHERE n.age >= 18 RETURN n.name",
    "MATCH (a:Person) OPTIONAL MATCH (a)-[:KNOWS]->(b) RETURN a.name, b.name",
    "MATCH (a:Person {name:'Ada'})-[:KNOWS]->{1,2}(b) RETURN b.name",
    "MATCH (n) RETURN n.label AS label, count(*) AS c",
    "MATCH (n) RETURN DISTINCT n.label AS l ORDER BY l",
    "MATCH p = (:Person)-[:KNOWS]->(:Person) RETURN path_length(p)",
    "MATCH (a:Person)-[:KNOWS]->()-[:KNOWS]->(c:Person) WHERE a.age >= 21 AND c.active = true RETURN a.name, c.name",
    "MATCH (n:Person) WHERE NOT n.name = 'Ada' RETURN n",
    "MATCH (n:Person) WHERE n.age >= 40 RETURN n.name ORDER BY n.age DESC OFFSET 1 LIMIT 2",
];
const MALFORMED: [&str; 4] = [
    "MATCH (n:Person RETURN n.name",
    "MATCH (a)-[:KNOWS]->(b) WHERE a.age > RETURN b.name",
    "MATCH (n:Person) RETRUN n.name",
    "MATCH (a:Person {name: })-[:KNOWS]->(b) WHERE b.age > (3 + ) RETURN b",
];

fn bench(name: &str, f: fn(&str) -> Vec<String>, qs: &[&str]) {
    for q in qs {
        let e = f(q);
        println!("{name} accept={} | {q}{}", e.is_empty(), if e.is_empty() { String::new() } else { format!("\n    {e:?}") });
    }
    let iters = 2_000;
    let mut rounds = vec![];
    for _ in 0..9 {
        let t = Instant::now();
        for _ in 0..iters { for q in qs { black_box(f(black_box(q))); } }
        rounds.push(t.elapsed().as_nanos() as f64 / (iters * qs.len()) as f64);
    }
    rounds.sort_by(|a, b| a.partial_cmp(b).unwrap());
    println!("{name}: median {:.0} ns/query, min {:.0} ns/query (warm: DFA cache shared across runs)", rounds[4], rounds[0]);
}

fn main() {
    #[cfg(feature = "cypher")]
    {
        let t = Instant::now();
        let e = parse_cypher(CYPHER[0]);
        println!("cypher first parse (cold DFA): {:?} errs={}", t.elapsed(), e.len());
        bench("antlr-cypher", parse_cypher, &CYPHER);
        for q in MALFORMED { println!("antlr-cypher malformed | {q}\n    {:?}", parse_cypher(q)); }
    }
    #[cfg(feature = "gql")]
    {
        let t = Instant::now();
        let e = parse_gql(GQL[0]);
        println!("gql first parse (cold DFA): {:?} errs={}", t.elapsed(), e.len());
        bench("antlr-gql", parse_gql, &GQL);
        for q in MALFORMED { println!("antlr-gql malformed | {q}\n    {:?}", parse_gql(q)); }
    }
}

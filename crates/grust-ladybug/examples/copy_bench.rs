//! Times the ways the `lbug` crate can bulk-load a graph, on one synthetic
//! graph, so the adapter's load path can be chosen from a measurement:
//!
//!   A. what `grust-ladybug` does today: register Arrow batches as a scratch
//!      table and `COPY t FROM (MATCH (x:scratch) RETURN …)`;
//!   B. `COPY t FROM scratch` over the registered table directly, the shape
//!      of Python's `COPY t FROM $df` (may be rejected: reported, not fatal);
//!   C. `COPY t FROM 'file.csv'`, the engine's native file path;
//!   D. C again with INT64 primary keys and no properties, the CSR-parquet
//!      shape the maintainer loads cit-Patents from in seconds;
//!   E. the CSR registration (`create_arrow_rel_table_csr`) with INT64 keys,
//!      copied through MATCH and directly.
//!
//!   cargo run --release -p grust-ladybug --example copy_bench -- [nodes] [edges]
//!
//! Prints one line per variant: rows, seconds, rows per second, or the
//! engine's error text.
use std::{fs::File, io::Write, sync::Arc, time::Instant};

use arrow::{
    array::{ArrayRef, Int64Array, StringArray},
    datatypes::{DataType, Field, Schema},
    record_batch::RecordBatch,
};

fn arg(i: usize, default: usize) -> usize {
    std::env::args()
        .nth(i)
        .and_then(|s| s.parse().ok())
        .unwrap_or(default)
}

fn strings(name: &str, values: &[String]) -> (Field, ArrayRef) {
    (
        Field::new(name, DataType::Utf8, false),
        Arc::new(StringArray::from_iter_values(values.iter().map(String::as_str))),
    )
}

fn ints(name: &str, values: &[i64]) -> (Field, ArrayRef) {
    (
        Field::new(name, DataType::Int64, false),
        Arc::new(Int64Array::from(values.to_vec())),
    )
}

fn batch(cols: Vec<(Field, ArrayRef)>) -> RecordBatch {
    let (fields, arrays): (Vec<_>, Vec<_>) = cols.into_iter().unzip();
    RecordBatch::try_new(Arc::new(Schema::new(fields)), arrays).expect("batch")
}

struct Bench<'a> {
    conn: &'a lbug::Connection<'a>,
}

impl Bench<'_> {
    fn q(&self, sql: &str) -> Result<(), String> {
        self.conn.query(sql).map(drop).map_err(|e| e.to_string())
    }

    /// Runs `f`, prints the variant's rate or the error it returned.
    fn time(&self, label: &str, rows: usize, f: impl FnOnce() -> Result<(), String>) {
        let t = Instant::now();
        match f() {
            Ok(()) => {
                let s = t.elapsed().as_secs_f64();
                println!("{label:58} {rows:>9} rows {s:8.2} s {:>10.0} rows/s", rows as f64 / s);
            }
            Err(e) => println!("{label:58} ERROR {}", e.lines().next().unwrap_or("")),
        }
    }
}

fn main() {
    let n = arg(1, 1_000_000);
    let m = arg(2, 5_000_000);
    let dir = tempfile::tempdir().expect("tempdir");
    let db = lbug::Database::new(dir.path().join("db"), lbug::SystemConfig::default()).expect("db");
    let conn = lbug::Connection::new(&db).expect("conn");
    let b = Bench { conn: &conn };
    println!(
        "lbug {} · {n} nodes, {m} edges · db in {}",
        env!("CARGO_PKG_VERSION"),
        dir.path().display()
    );

    // ---- the data: string ids like the adapter's, and their integer twins
    let ids: Vec<String> = (0..n).map(|i| format!("n{i}")).collect();
    let empty: Vec<String> = vec!["{}".to_string(); n];
    let from_i: Vec<i64> = (0..m).map(|i| ((i * 7919) % n) as i64).collect();
    let to_i: Vec<i64> = (0..m).map(|i| ((i * 104_729 + 13) % n) as i64).collect();
    let from_s: Vec<String> = from_i.iter().map(|i| format!("n{i}")).collect();
    let to_s: Vec<String> = to_i.iter().map(|i| format!("n{i}")).collect();
    let eids: Vec<String> = (0..m).map(|i| format!("e{i}")).collect();
    let eprops: Vec<String> = vec!["{}".to_string(); m];

    // ---- string-keyed tables, the adapter's schema
    for t in ["N", "N2", "N3"] {
        b.q(&format!("CREATE NODE TABLE {t}(id STRING, props STRING, PRIMARY KEY(id));")).unwrap();
    }
    for (e, t) in [("E", "N"), ("E2", "N"), ("E3", "N")] {
        b.q(&format!("CREATE REL TABLE {e}(FROM {t} TO {t}, id STRING, props STRING);")).unwrap();
    }

    // A. registered Arrow + COPY FROM (MATCH …): the adapter today
    let node_batch = batch(vec![strings("id", &ids), strings("props", &empty)]);
    b.time("A nodes: arrow table, COPY FROM (MATCH …)", n, || {
        conn.create_arrow_table("s_nodes", &[node_batch.clone()]).map_err(|e| e.to_string())?;
        let r = b.q("COPY N FROM (MATCH (x:s_nodes) RETURN x.id, x.props);");
        conn.drop_arrow_table("s_nodes").map_err(|e| e.to_string())?;
        r
    });
    let rel_batch = batch(vec![
        strings("from", &from_s),
        strings("to", &to_s),
        strings("id", &eids),
        strings("props", &eprops),
    ]);
    b.time("A edges: arrow rel table, COPY FROM (MATCH …)", m, || {
        conn.create_arrow_rel_table("s_rels", &[rel_batch.clone()], "N", "N")
            .map_err(|e| e.to_string())?;
        let r = b.q("COPY E FROM (MATCH (a:N)-[r:s_rels]->(b:N) RETURN a.id, b.id, r.id, r.props);");
        conn.drop_arrow_table("s_rels").map_err(|e| e.to_string())?;
        r
    });

    // B. COPY t FROM <registered table> directly
    b.time("B nodes: arrow table, COPY FROM s_nodes", n, || {
        conn.create_arrow_table("s_nodes", &[node_batch.clone()]).map_err(|e| e.to_string())?;
        let r = b.q("COPY N2 FROM s_nodes;");
        conn.drop_arrow_table("s_nodes").map_err(|e| e.to_string())?;
        r
    });
    b.time("B edges: arrow rel table, COPY FROM s_rels", m, || {
        conn.create_arrow_rel_table("s_rels", &[rel_batch.clone()], "N2", "N2")
            .map_err(|e| e.to_string())?;
        let r = b.q("COPY E2 FROM s_rels;");
        conn.drop_arrow_table("s_rels").map_err(|e| e.to_string())?;
        r
    });

    // C. CSV files, string keys
    let nodes_csv = dir.path().join("nodes.csv");
    let rels_csv = dir.path().join("rels.csv");
    {
        let mut f = File::create(&nodes_csv).unwrap();
        for id in &ids {
            writeln!(f, "{id},{{}}").unwrap();
        }
        let mut f = File::create(&rels_csv).unwrap();
        for i in 0..m {
            writeln!(f, "{},{},{},{{}}", from_s[i], to_s[i], eids[i]).unwrap();
        }
    }
    b.time("C nodes: COPY FROM 'nodes.csv' (STRING keys)", n, || {
        b.q(&format!("COPY N3 FROM '{}';", nodes_csv.display()))
    });
    b.time("C edges: COPY FROM 'rels.csv' (STRING keys)", m, || {
        b.q(&format!("COPY E3 FROM '{}';", rels_csv.display()))
    });

    // D. CSV files, INT64 keys, no properties: the CSR-parquet shape
    b.q("CREATE NODE TABLE NI(id INT64, PRIMARY KEY(id));").unwrap();
    for e in ["EI", "EI2", "EI3"] {
        b.q(&format!("CREATE REL TABLE {e}(FROM NI TO NI);")).unwrap();
    }
    let nodes_i_csv = dir.path().join("nodes_i.csv");
    let rels_i_csv = dir.path().join("rels_i.csv");
    {
        let mut f = File::create(&nodes_i_csv).unwrap();
        for i in 0..n {
            writeln!(f, "{i}").unwrap();
        }
        let mut f = File::create(&rels_i_csv).unwrap();
        for i in 0..m {
            writeln!(f, "{},{}", from_i[i], to_i[i]).unwrap();
        }
    }
    b.time("D nodes: COPY FROM 'nodes_i.csv' (INT64 keys)", n, || {
        b.q(&format!("COPY NI FROM '{}';", nodes_i_csv.display()))
    });
    b.time("D edges: COPY FROM 'rels_i.csv' (INT64 keys, no props)", m, || {
        b.q(&format!("COPY EI FROM '{}';", rels_i_csv.display()))
    });

    // E. CSR registration with INT64 keys: indices sorted by source, indptr offsets
    let mut order: Vec<usize> = (0..m).collect();
    order.sort_by_key(|&i| from_i[i]);
    let indices: Vec<i64> = order.iter().map(|&i| to_i[i]).collect();
    let mut indptr: Vec<i64> = vec![0; n + 1];
    for &i in &order {
        indptr[from_i[i] as usize + 1] += 1;
    }
    for i in 0..n {
        indptr[i + 1] += indptr[i];
    }
    let indices_batch = batch(vec![ints("to", &indices)]);
    let indptr_batch = batch(vec![ints("offset", &indptr)]);
    b.time("E edges: CSR arrow rel table, COPY FROM (MATCH …)", m, || {
        conn.create_arrow_rel_table_csr("s_csr", &[indices_batch.clone()], &[indptr_batch.clone()], "NI", "NI", "to")
            .map_err(|e| e.to_string())?;
        let r = b.q("COPY EI2 FROM (MATCH (a:NI)-[r:s_csr]->(b:NI) RETURN a.id, b.id);");
        conn.drop_arrow_table("s_csr").map_err(|e| e.to_string())?;
        r
    });
    b.time("E edges: CSR arrow rel table, COPY FROM s_csr", m, || {
        conn.create_arrow_rel_table_csr("s_csr", &[indices_batch.clone()], &[indptr_batch.clone()], "NI", "NI", "to")
            .map_err(|e| e.to_string())?;
        let r = b.q("COPY EI3 FROM s_csr;");
        conn.drop_arrow_table("s_csr").map_err(|e| e.to_string())?;
        r
    });

    // sanity: what landed
    for (t, want) in [("N", n), ("N2", n), ("N3", n), ("NI", n), ("E", m), ("E2", m), ("E3", m), ("EI", m), ("EI2", m), ("EI3", m)] {
        let pat = if t.starts_with('E') { format!("MATCH ()-[r:{t}]->() RETURN count(r);") } else { format!("MATCH (x:{t}) RETURN count(x);") };
        let got = conn
            .query(&pat)
            .ok()
            .and_then(|mut r| r.next())
            .map(|row| format!("{:?}", row[0]))
            .unwrap_or_else(|| "?".into());
        println!("count {t:4} = {got} (want {want})");
    }
}

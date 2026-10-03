//! Substrait for Grust: a small, decisive experiment on DataFusion 55.1.0.
//!
//! 1. A two-hop plan built by hand in Substrait runs on DataFusion and gives
//!    the same rows as the equivalent SQL (selective rows, and a full-graph
//!    aggregate).
//! 2. For each relational shape Grust's pushdowns emit today, SQL is planned,
//!    produced to Substrait, consumed back and executed, and unparsed to SQL;
//!    results are compared with the SQL run.
//! 3. A non-standard function (JSON property access) is produced and consumed
//!    in a session that lacks it.
//!
//! Usage: substrait-two-hop <data dir> <raw output dir>

mod handbuilt;

use datafusion::arrow::array::{Array, ArrayRef, RecordBatch, StringArray, StringBuilder};
use datafusion::arrow::datatypes::DataType;
use datafusion::arrow::util::display::{ArrayFormatter, FormatOptions};
use datafusion::common::Result;
use datafusion::logical_expr::{ColumnarValue, LogicalPlan, Volatility, create_udf};
use datafusion::physical_plan::displayable;
use datafusion::prelude::*;
use datafusion_substrait::logical_plan::{consumer, producer};
use datafusion_substrait::substrait::proto::Plan;
use datafusion_substrait::substrait::proto::extensions::simple_extension_declaration::MappingType;
use prost::Message;
use serde_json::json;
use std::collections::hash_map::DefaultHasher;
use std::hash::{Hash, Hasher};
use std::io::Write;
use std::sync::Arc;
use std::time::Instant;

const LO: i64 = 4_000_000;
const HI: i64 = 4_002_000;

/// Order-independent digest: rows rendered as text, sorted, hashed.
fn digest(batches: &[RecordBatch]) -> (usize, String) {
    let opts = FormatOptions::default().with_null("NULL");
    let mut rows = Vec::new();
    for b in batches {
        let fmts: Vec<_> = b
            .columns()
            .iter()
            .map(|c| ArrayFormatter::try_new(c.as_ref(), &opts).unwrap())
            .collect();
        for r in 0..b.num_rows() {
            rows.push(
                fmts.iter()
                    .map(|f| f.value(r).to_string())
                    .collect::<Vec<_>>()
                    .join("|"),
            );
        }
    }
    rows.sort();
    let mut h = DefaultHasher::new();
    rows.hash(&mut h);
    (rows.len(), format!("{:016x}", h.finish()))
}

fn first_rows(batches: &[RecordBatch], n: usize) -> Vec<String> {
    let opts = FormatOptions::default().with_null("NULL");
    let mut rows = Vec::new();
    for b in batches {
        let fmts: Vec<_> = b
            .columns()
            .iter()
            .map(|c| ArrayFormatter::try_new(c.as_ref(), &opts).unwrap())
            .collect();
        for r in 0..b.num_rows() {
            rows.push(
                fmts.iter()
                    .map(|f| f.value(r).to_string())
                    .collect::<Vec<_>>()
                    .join("|"),
            );
        }
    }
    rows.sort();
    rows.truncate(n);
    rows
}

/// `json_get_str(props, key)`: a stand-in for the JSON property access Grust
/// emits as `json_extract` / `GET_JSON_OBJECT` / `#>>`. Not a Substrait
/// standard function and not a DataFusion built-in.
fn json_get_str_udf() -> datafusion::logical_expr::ScalarUDF {
    create_udf(
        "json_get_str",
        vec![DataType::Utf8, DataType::Utf8],
        DataType::Utf8,
        Volatility::Immutable,
        Arc::new(|args: &[ColumnarValue]| {
            let arrays = ColumnarValue::values_to_arrays(args)?;
            let props = arrays[0].as_any().downcast_ref::<StringArray>().unwrap();
            let keys = arrays[1].as_any().downcast_ref::<StringArray>().unwrap();
            let mut out = StringBuilder::new();
            for i in 0..props.len() {
                if props.is_null(i) || keys.is_null(i) {
                    out.append_null();
                    continue;
                }
                let v: serde_json::Value =
                    serde_json::from_str(props.value(i)).unwrap_or(serde_json::Value::Null);
                match v.get(keys.value(i)).and_then(|x| x.as_str()) {
                    Some(s) => out.append_value(s),
                    None => out.append_null(),
                }
            }
            Ok(ColumnarValue::Array(Arc::new(out.finish()) as ArrayRef))
        }),
    )
}

async fn context(data: &str, with_udf: bool) -> Result<SessionContext> {
    let cfg = SessionConfig::new().with_target_partitions(4);
    let ctx = SessionContext::new_with_config(cfg);
    ctx.register_parquet(
        "v",
        &format!("{data}/cit-Patents-v.parquet"),
        ParquetReadOptions::default(),
    )
    .await?;
    ctx.register_parquet(
        "e",
        &format!("{data}/cit-Patents-e.parquet"),
        ParquetReadOptions::default(),
    )
    .await?;
    // Small property tables for JSON and map access.
    ctx.sql(
        "CREATE TABLE np AS SELECT * FROM (VALUES \
         (1, 'Person', '{\"name\":\"alice\"}'), (2, 'Person', '{\"name\":\"bob\"}'), \
         (3, 'City', '{\"name\":\"rome\"}')) AS t(id, label, props)",
    )
    .await?
    .collect()
    .await?;
    ctx.sql(
        "CREATE TABLE npm AS SELECT id, map(['name'], [name]) AS m FROM (VALUES \
         (1, 'alice'), (2, 'bob')) AS t(id, name)",
    )
    .await?
    .collect()
    .await?;
    if with_udf {
        ctx.register_udf(json_get_str_udf());
    }
    Ok(ctx)
}

async fn run_plan(ctx: &SessionContext, plan: LogicalPlan) -> Result<Vec<RecordBatch>> {
    ctx.execute_logical_plan(plan).await?.collect().await
}

/// Extension function declarations whose URN reference does not resolve to a
/// declared URN in the plan.
fn dangling_urn_refs(plan: &Plan) -> (usize, usize) {
    let anchors: Vec<u32> = plan
        .extension_urns
        .iter()
        .map(|u| u.extension_urn_anchor)
        .collect();
    let mut total = 0;
    let mut dangling = 0;
    for ext in &plan.extensions {
        if let Some(MappingType::ExtensionFunction(f)) = &ext.mapping_type {
            total += 1;
            if !anchors.contains(&f.extension_urn_reference) {
                dangling += 1;
            }
        }
    }
    (total, dangling)
}

fn err_line(e: impl std::fmt::Display) -> String {
    let s = e.to_string();
    let s = s.lines().next().unwrap_or("").to_string();
    if s.len() > 220 { format!("{}...", &s[..220]) } else { s }
}

#[tokio::main(flavor = "multi_thread", worker_threads = 4)]
async fn main() -> Result<()> {
    let args: Vec<String> = std::env::args().collect();
    let data = args.get(1).expect("data dir");
    let raw = args.get(2).expect("raw dir");
    std::fs::create_dir_all(format!("{raw}/df-produced")).unwrap();
    let ctx = context(data, true).await?;
    let mut log = std::fs::File::create(format!("{raw}/experiment-log.txt")).unwrap();
    macro_rules! say {
        ($($t:tt)*) => {{ let s = format!($($t)*); println!("{s}"); writeln!(log, "{s}").unwrap(); }};
    }
    say!(
        "versions: datafusion {} ; datafusion-substrait 55.1.0 ; substrait crate 0.63.0 (spec {:?})",
        datafusion::DATAFUSION_VERSION,
        datafusion_substrait::substrait::version::version()
    );

    // ---------------------------------------------------------------- part 1
    say!("\n== Part 1: hand-built Substrait two-hop vs SQL ==");
    let sql_rows = format!(
        "SELECT n0.id AS a, n1.id AS b, n2.id AS c FROM v n0 \
         JOIN e e0 ON e0.source = n0.id JOIN v n1 ON n1.id = e0.target \
         JOIN e e1 ON e1.source = n1.id JOIN v n2 ON n2.id = e1.target \
         WHERE n0.id >= {LO} AND n0.id < {HI}"
    );
    let t = Instant::now();
    let sql_batches = ctx.sql(&sql_rows).await?.collect().await?;
    let sql_ms = t.elapsed().as_millis();
    let hb = handbuilt::two_hop_rows(LO, HI);
    let hb_bytes = hb.encode_to_vec();
    std::fs::write(format!("{raw}/handbuilt-two-hop-rows.bin"), &hb_bytes).unwrap();
    std::fs::write(
        format!("{raw}/handbuilt-two-hop-rows.json"),
        serde_json::to_string_pretty(&hb).unwrap(),
    )
    .unwrap();
    let decoded = Plan::decode(hb_bytes.as_slice()).expect("decode");
    let t = Instant::now();
    let lp = consumer::from_substrait_plan(&ctx.state(), &decoded).await?;
    let hb_batches = run_plan(&ctx, lp.clone()).await?;
    let hb_ms = t.elapsed().as_millis();
    let (sn, sd) = digest(&sql_batches);
    let (hn, hd) = digest(&hb_batches);
    say!("SQL      : {sn} rows, digest {sd}, {sql_ms} ms");
    say!("Substrait: {hn} rows, digest {hd}, {hb_ms} ms, plan {} bytes", hb_bytes.len());
    say!("same rows: {}", sn == hn && sd == hd);
    say!("first rows (sorted): {:?}", first_rows(&hb_batches, 3));
    // Variant: the filter above the joins, where SQL's WHERE sits.
    let top = handbuilt::two_hop_rows_filter_on_top(LO, HI);
    std::fs::write(
        format!("{raw}/handbuilt-two-hop-rows-filter-on-top.json"),
        serde_json::to_string_pretty(&top).unwrap(),
    )
    .unwrap();
    let t = Instant::now();
    let lp_top = consumer::from_substrait_plan(&ctx.state(), &top).await?;
    let top_batches = run_plan(&ctx, lp_top.clone()).await?;
    let top_ms = t.elapsed().as_millis();
    let (tn, td) = digest(&top_batches);
    say!("Substrait, filter above joins: {tn} rows, digest {td}, {top_ms} ms; same rows: {}", tn == sn && td == sd);
    // Timing, five runs each, after warm-up (single process, shared laptop).
    for (label, which) in [("SQL", 0), ("Substrait filter on n0 read", 1), ("Substrait filter above joins", 2)] {
        let mut ms = Vec::new();
        for _ in 0..5 {
            let t = Instant::now();
            let _ = match which {
                0 => ctx.sql(&sql_rows).await?.collect().await?,
                1 => run_plan(&ctx, consumer::from_substrait_plan(&ctx.state(), &decoded).await?).await?,
                _ => run_plan(&ctx, consumer::from_substrait_plan(&ctx.state(), &top).await?).await?,
            };
            ms.push(t.elapsed().as_millis());
        }
        say!("timing {label}: {ms:?} ms (plan + execute)");
    }
    let phys_top = ctx.state().create_physical_plan(&lp_top).await?;
    std::fs::write(
        format!("{raw}/handbuilt-two-hop-filter-on-top-physical.txt"),
        format!("{}", displayable(phys_top.as_ref()).indent(true)),
    )
    .unwrap();
    let opt = ctx.state().optimize(&lp)?;
    let phys = ctx.state().create_physical_plan(&lp).await?;
    let sql_phys = ctx.sql(&sql_rows).await?.create_physical_plan().await?;
    std::fs::write(
        format!("{raw}/handbuilt-two-hop-plans.txt"),
        format!(
            "-- logical plan from the Substrait consumer\n{}\n\n-- after DataFusion's optimizer\n{}\n\n\
             -- physical plan (Substrait route)\n{}\n\n-- physical plan (SQL route)\n{}\n",
            lp.display_indent(),
            opt.display_indent(),
            displayable(phys.as_ref()).indent(true),
            displayable(sql_phys.as_ref()).indent(true)
        ),
    )
    .unwrap();

    say!("\n-- full graph: count(*), sum(a), sum(b), sum(c) over every two-hop path");
    let sql_agg = "SELECT COUNT(*) AS paths, SUM(n0.id) AS sum_a, SUM(n1.id) AS sum_b, SUM(n2.id) AS sum_c \
                   FROM v n0 JOIN e e0 ON e0.source = n0.id JOIN v n1 ON n1.id = e0.target \
                   JOIN e e1 ON e1.source = n1.id JOIN v n2 ON n2.id = e1.target";
    let t = Instant::now();
    let a1 = ctx.sql(sql_agg).await?.collect().await?;
    let a1_ms = t.elapsed().as_millis();
    let hba = handbuilt::two_hop_aggregate();
    std::fs::write(
        format!("{raw}/handbuilt-two-hop-aggregate.json"),
        serde_json::to_string_pretty(&hba).unwrap(),
    )
    .unwrap();
    std::fs::write(format!("{raw}/handbuilt-two-hop-aggregate.bin"), hba.encode_to_vec()).unwrap();
    let t = Instant::now();
    let lpa = consumer::from_substrait_plan(&ctx.state(), &hba).await?;
    let a2 = run_plan(&ctx, lpa).await?;
    let a2_ms = t.elapsed().as_millis();
    say!("SQL      : {:?} ({a1_ms} ms)", first_rows(&a1, 1));
    say!("Substrait: {:?} ({a2_ms} ms)", first_rows(&a2, 1));
    say!("same: {}", first_rows(&a1, 1) == first_rows(&a2, 1));

    // ---------------------------------------------------------------- part 2
    say!("\n== Part 2: Grust's SQL shapes through producer -> consumer -> unparser ==");
    let queries: Vec<(&str, &str, String)> = vec![
        ("Q01", "node scan, filter, ORDER BY, LIMIT/OFFSET",
         "SELECT id FROM v WHERE id >= 4000000 AND id < 4000100 ORDER BY id LIMIT 10 OFFSET 2".into()),
        ("Q02", "fixed segment: inner-join chain (two hops)", sql_rows.clone()),
        ("Q03", "multi-pattern: comma join, conditions in WHERE",
         "SELECT n0.id, n1.id AS b, n2.id AS c FROM v n0, v n1, v n2, e e0, e e1 \
          WHERE e0.source = n0.id AND e0.target = n1.id AND e1.source = n0.id \
          AND e1.target = n2.id AND n0.id >= 4000000 AND n0.id < 4000200".into()),
        ("Q04", "OPTIONAL MATCH: LEFT JOIN to a subquery",
         "SELECT n0.id, opt.b FROM v n0 LEFT JOIN (SELECT e0.source AS anchor, n1.id AS b \
          FROM e e0 JOIN v n1 ON n1.id = e0.target) opt ON opt.anchor = n0.id \
          WHERE n0.id >= 4000000 AND n0.id < 4000200".into()),
        ("Q05", "undirected segment: OR join condition",
         "SELECT n0.id, n1.id AS b FROM v n0 JOIN e e0 ON (e0.source = n0.id OR e0.target = n0.id) \
          JOIN v n1 ON ((e0.source = n0.id AND n1.id = e0.target) OR (e0.target = n0.id AND n1.id = e0.source)) \
          WHERE n0.id >= 4000000 AND n0.id < 4000050".into()),
        ("Q06", "UNION (distinct)",
         "SELECT source AS x FROM e WHERE source < 3900000 UNION SELECT target AS x FROM e WHERE target < 3860000".into()),
        ("Q07", "UNION ALL",
         "SELECT source AS x FROM e WHERE source < 3870000 UNION ALL SELECT target AS x FROM e WHERE target < 3860000".into()),
        ("Q08", "scalar COUNT(*) over a join",
         "SELECT COUNT(*) FROM v n0 JOIN e e0 ON e0.source = n0.id JOIN v n1 ON n1.id = e0.target".into()),
        ("Q09", "SELECT DISTINCT (catalog procedures)",
         "SELECT DISTINCT source FROM e WHERE source < 3900000 ORDER BY source".into()),
        ("Q10", "GROUP BY aggregate (degree)",
         "SELECT source, COUNT(*) AS deg FROM e WHERE source < 3900000 GROUP BY source".into()),
        ("Q11", "correlated scalar subquery with MIN (shortest-path tie-break shape)",
         "SELECT c.source, c.target FROM e c WHERE c.source < 3870000 AND \
          c.target = (SELECT MIN(q.target) FROM e q WHERE q.source = c.source)".into()),
        ("Q12", "EXISTS subquery",
         "SELECT id FROM v WHERE id < 3900000 AND EXISTS (SELECT 1 FROM e WHERE e.source = v.id)".into()),
        ("Q13", "NOT IN subquery",
         "SELECT id FROM v WHERE id < 3900000 AND id NOT IN (SELECT target FROM e)".into()),
        ("Q14", "window: row_number() OVER (ORDER BY id) - 1 (dense ids)",
         "SELECT id, row_number() OVER (ORDER BY id) - 1 AS dense FROM v WHERE id < 3900000".into()),
        ("Q15", "CASE (undirected walk step)",
         "SELECT CASE WHEN source = 4000000 THEN target ELSE source END AS other FROM e \
          WHERE source = 4000000 OR target = 4000000".into()),
        ("Q16", "string ops: starts_with, strpos, ||, encode hex (walk tokens)",
         "SELECT id, '|' || encode(CAST(id AS VARCHAR), 'hex') || '|' AS tok FROM np \
          WHERE starts_with(label, 'Per') AND strpos(label, 'son') > 0".into()),
        ("Q17", "JSON property access (json_get_str UDF)",
         "SELECT id FROM np WHERE json_get_str(props, 'name') = 'alice'".into()),
        ("Q18", "map property access m['name']",
         "SELECT id, m['name'] AS name FROM npm".into()),
        ("Q19", "WITH RECURSIVE bounded walk (variable-length path)",
         "WITH RECURSIVE walk(s, x, depth) AS (SELECT id AS s, id AS x, 0 AS depth FROM v WHERE id = 4000000 \
          UNION ALL SELECT w.s, ed.target, w.depth + 1 FROM walk w JOIN e ed ON ed.source = w.x \
          WHERE w.depth + 1 <= 3) SELECT s, x, depth FROM walk".into()),
    ];
    let mut jsonl = std::fs::File::create(format!("{raw}/coverage.jsonl")).unwrap();
    say!("{:<4} | {:<62} | {:>7} | {:<8} | {:<8} | {:<10} | {:<8}", "id", "shape", "rows", "produce", "consume", "urn refs", "unparse");
    for (id, shape, sql) in &queries {
        let mut rec = json!({"id": id, "shape": shape, "sql": sql});
        let sql_res = async { ctx.sql(sql).await?.collect().await }.await;
        let (n, d) = match &sql_res {
            Ok(b) => digest(b),
            Err(e) => {
                rec["sql_error"] = json!(err_line(e));
                (0, String::new())
            }
        };
        rec["sql_rows"] = json!(n);
        rec["sql_digest"] = json!(d);
        let plan = match async { ctx.sql(sql).await?.into_optimized_plan() }.await {
            Ok(p) => p,
            Err(e) => {
                rec["plan_error"] = json!(err_line(e));
                writeln!(jsonl, "{}", rec).unwrap();
                say!("{id:<4} | {shape:<62} | planning error");
                continue;
            }
        };
        let produced = producer::to_substrait_plan(&plan, &ctx.state());
        let (mut produce, mut consume, mut urn, mut unparse) =
            ("error".to_string(), "-".to_string(), "-".to_string(), "-".to_string());
        match produced {
            Err(e) => rec["produce_error"] = json!(err_line(e)),
            Ok(p) => {
                produce = "ok".into();
                let bytes = p.encode_to_vec();
                rec["plan_bytes"] = json!(bytes.len());
                let (total, dangling) = dangling_urn_refs(&p);
                urn = format!("{dangling}/{total} dangl.");
                rec["extension_functions"] = json!(total);
                rec["dangling_urn_refs"] = json!(dangling);
                rec["extension_urns_declared"] = json!(p.extension_urns.len());
                std::fs::write(
                    format!("{raw}/df-produced/{id}.json"),
                    serde_json::to_string(&*p).unwrap(),
                )
                .unwrap();
                let decoded = Plan::decode(bytes.as_slice()).unwrap();
                match consumer::from_substrait_plan(&ctx.state(), &decoded).await {
                    Err(e) => {
                        consume = "error".into();
                        rec["consume_error"] = json!(err_line(e));
                    }
                    Ok(lp) => match run_plan(&ctx, lp.clone()).await {
                        Err(e) => {
                            consume = "exec err".into();
                            rec["consume_exec_error"] = json!(err_line(e));
                        }
                        Ok(b) => {
                            let (n2, d2) = digest(&b);
                            consume = if n2 == n && d2 == d { "same".into() } else { "DIFFERS".into() };
                            rec["consumed_rows"] = json!(n2);
                            rec["consumed_digest"] = json!(d2);
                            match datafusion::sql::unparser::plan_to_sql(&lp) {
                                Err(e) => {
                                    unparse = "error".into();
                                    rec["unparse_error"] = json!(err_line(e));
                                }
                                Ok(stmt) => {
                                    let text = stmt.to_string();
                                    rec["unparsed_sql"] = json!(text);
                                    match async { ctx.sql(&text).await?.collect().await }.await {
                                        Err(e) => {
                                            unparse = "exec err".into();
                                            rec["unparse_exec_error"] = json!(err_line(e));
                                        }
                                        Ok(b) => {
                                            let (n3, d3) = digest(&b);
                                            unparse = if n3 == n && d3 == d { "same".into() } else { "DIFFERS".into() };
                                        }
                                    }
                                }
                            }
                        }
                    },
                }
            }
        }
        rec["produce"] = json!(produce);
        rec["consume"] = json!(consume);
        rec["unparse"] = json!(unparse);
        writeln!(jsonl, "{}", rec).unwrap();
        say!("{id:<4} | {shape:<62} | {n:>7} | {produce:<8} | {consume:<8} | {urn:<10} | {unparse:<8}");
    }

    // ---------------------------------------------------------------- part 3
    say!("\n== Part 3: a plan that names a non-standard function, consumed elsewhere ==");
    let q = "SELECT id FROM np WHERE json_get_str(props, 'name') = 'alice'";
    let p = producer::to_substrait_plan(&ctx.sql(q).await?.into_optimized_plan()?, &ctx.state())?;
    for ext in &p.extensions {
        if let Some(MappingType::ExtensionFunction(f)) = &ext.mapping_type {
            say!(
                "declared function: name={:?} anchor={} extension_urn_reference={} (declared URNs: {})",
                f.name, f.function_anchor, f.extension_urn_reference, p.extension_urns.len()
            );
        }
    }
    let bare = context(data, false).await?;
    match consumer::from_substrait_plan(&bare.state(), &p).await {
        Ok(_) => say!("consumer without the UDF: accepted (unexpected)"),
        Err(e) => say!("consumer without the UDF: {}", err_line(e)),
    }
    say!("\ndone");
    Ok(())
}

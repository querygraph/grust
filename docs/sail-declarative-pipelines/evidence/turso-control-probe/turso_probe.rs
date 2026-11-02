//! Throwaway qualification probe: does Turso 0.7.2 MVCC give the guard-row
//! property CDC-CONTROL-STORE-DESIGN.md needs? Not product code.
use std::io::Write as _;
use std::sync::Arc;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;

use turso::{Builder, Connection, Database};

type R<T = ()> = Result<T, Box<dyn std::error::Error + Send + Sync>>;

async fn open(path: &str) -> R<Database> {
    Ok(Builder::new_local(path).build().await?)
}

async fn conn(db: &Database) -> R<Connection> {
    let c = db.connect()?;
    let _ = c.execute_batch("PRAGMA journal_mode=mvcc;").await;
    c.busy_timeout(Duration::from_secs(10))?;
    Ok(c)
}

async fn one(c: &Connection, sql: &str) -> R<i64> {
    let mut rows = c.query(sql, ()).await?;
    let row = rows.next().await?.ok_or("no row")?;
    Ok(row.get(0)?)
}

async fn text(c: &Connection, sql: &str) -> R<String> {
    let mut rows = c.query(sql, ()).await?;
    let row = rows.next().await?.ok_or("no row")?;
    Ok(format!("{:?}", row.get_value(0)?))
}

async fn schema(c: &Connection) -> R {
    c.execute_batch(
        "CREATE TABLE g(id INTEGER PRIMARY KEY, epoch INTEGER, revision INTEGER);
         CREATE TABLE head(id INTEGER PRIMARY KEY, version INTEGER);
         CREATE TABLE receipt(revision INTEGER PRIMARY KEY, epoch INTEGER, version INTEGER);
         CREATE TABLE takeover(revision INTEGER PRIMARY KEY, epoch INTEGER);
         INSERT INTO g VALUES (1, 1, 0);
         INSERT INTO head VALUES (1, 0);",
    )
    .await?;
    Ok(())
}

fn retryable(e: &turso::Error) -> bool {
    let s = e.to_string();
    matches!(e, turso::Error::Busy(_) | turso::Error::BusySnapshot(_))
        || s.contains("database is locked")
        || s.contains("Write-write conflict")
        || s.contains("Commit dependency aborted")
}

/// Ratify in one transaction; `Ok(false)` means fenced.
async fn ratify_body(c: &Connection, epoch: i64) -> Result<Option<i64>, turso::Error> {
    let changed = c
        .execute(
            format!("UPDATE g SET revision = revision + 1 WHERE id = 1 AND epoch = {epoch}"),
            (),
        )
        .await?;
    if changed == 0 {
        return Ok(None);
    }
    c.execute("UPDATE head SET version = version + 1 WHERE id = 1", ())
        .await?;
    let mut rows = c
        .query("SELECT g.revision, head.version FROM g, head", ())
        .await?;
    let row = rows.next().await?.ok_or(turso::Error::Error("row".into()))?;
    let (revision, version): (i64, i64) = (row.get(0)?, row.get(1)?);
    drop(rows);
    c.execute(
        format!("INSERT INTO receipt VALUES ({revision}, {epoch}, {version})"),
        (),
    )
    .await?;
    Ok(Some(revision))
}

async fn takeover_body(c: &Connection) -> Result<i64, turso::Error> {
    c.execute(
        "UPDATE g SET epoch = epoch + 1, revision = revision + 1 WHERE id = 1",
        (),
    )
    .await?;
    let mut rows = c.query("SELECT revision, epoch FROM g", ()).await?;
    let row = rows.next().await?.ok_or(turso::Error::Error("row".into()))?;
    let (revision, epoch): (i64, i64) = (row.get(0)?, row.get(1)?);
    drop(rows);
    c.execute(format!("INSERT INTO takeover VALUES ({revision}, {epoch})"), ())
        .await?;
    Ok(epoch)
}

async fn txn<T>(c: &Connection, body: impl AsyncFn(&Connection) -> Result<T, turso::Error>, retries: &AtomicU64) -> R<T> {
    for _ in 0..10_000 {
        if let Err(e) = c.execute_batch("BEGIN CONCURRENT").await {
            if retryable(&e) {
                retries.fetch_add(1, Ordering::Relaxed);
                continue;
            }
            return Err(e.into());
        }
        let result = match body(c).await {
            Ok(v) => c.execute_batch("COMMIT").await.map(|()| v),
            Err(e) => Err(e),
        };
        match result {
            Ok(v) => return Ok(v),
            Err(e) if retryable(&e) => {
                let _ = c.execute_batch("ROLLBACK").await;
                retries.fetch_add(1, Ordering::Relaxed);
                tokio::time::sleep(Duration::from_micros(200)).await;
            }
            Err(e) => {
                let _ = c.execute_batch("ROLLBACK").await;
                return Err(e.into());
            }
        }
    }
    Err("retries exhausted".into())
}

/// A: the ratifier reads the guard, a takeover commits, the ratifier then
/// mutates the guard. C: same, but the ratifier never mutates the guard.
async fn interleavings(dir: &str) -> R {
    for (name, mutate_guard) in [("A guard-mutating ratify", true), ("C read-only guard control", false)] {
        let db = open(&format!("{dir}/inter-{mutate_guard}.db")).await?;
        let (a, b) = (conn(&db).await?, conn(&db).await?);
        schema(&a).await?;
        a.execute_batch("BEGIN CONCURRENT").await?;
        let seen = one(&a, "SELECT epoch FROM g").await?;
        b.execute_batch("BEGIN CONCURRENT").await?;
        takeover_body(&b).await?;
        b.execute_batch("COMMIT").await?;
        let outcome = async {
            if mutate_guard {
                let r = ratify_body(&a, seen).await?;
                if r.is_none() {
                    return Ok::<_, turso::Error>("fenced: guard update matched zero rows".to_string());
                }
            } else {
                a.execute("UPDATE head SET version = version + 1 WHERE id = 1", ()).await?;
                a.execute(format!("INSERT INTO receipt VALUES (1, {seen}, 1)"), ()).await?;
            }
            a.execute_batch("COMMIT").await?;
            Ok("COMMITTED under the stale epoch".to_string())
        }
        .await;
        let _ = a.execute_batch("ROLLBACK").await;
        let c = conn(&db).await?;
        println!(
            "{name}: {} | epoch={} head={} receipts={}",
            match outcome { Ok(s) => s, Err(e) => format!("error: {e}") },
            one(&c, "SELECT epoch FROM g").await?,
            one(&c, "SELECT version FROM head").await?,
            one(&c, "SELECT count(*) FROM receipt").await?,
        );
    }
    // B: the ratifier mutates first; the takeover then runs against it.
    let db = open(&format!("{dir}/inter-b.db")).await?;
    let (a, b) = (conn(&db).await?, conn(&db).await?);
    schema(&a).await?;
    b.busy_timeout(Duration::from_millis(50))?;
    a.execute_batch("BEGIN CONCURRENT").await?;
    ratify_body(&a, 1).await?;
    b.execute_batch("BEGIN CONCURRENT").await?;
    let eager = takeover_body(&b).await;
    println!("B takeover against an open ratify: {:?}", eager.map_err(|e| e.to_string()));
    let _ = b.execute_batch("ROLLBACK").await;
    a.execute_batch("COMMIT").await?;
    println!("B ratify commit ok; head={}", one(&b, "SELECT version FROM head").await?);
    Ok(())
}

/// Workers ratify under a token read outside the transaction; one bumps the
/// epoch. Every receipt must carry the epoch in force at its revision.
async fn race(dir: &str, workers: usize, ops: u64) -> R {
    let db = Arc::new(open(&format!("{dir}/race.db")).await?);
    schema(&conn(&db).await?).await?;
    let retries = Arc::new(AtomicU64::new(0));
    let (acked, fenced, taken) = (
        Arc::new(AtomicU64::new(0)),
        Arc::new(AtomicU64::new(0)),
        Arc::new(AtomicU64::new(0)),
    );
    let mut tasks = Vec::new();
    for w in 0..workers {
        let (db, retries, acked, fenced, taken) = (db.clone(), retries.clone(), acked.clone(), fenced.clone(), taken.clone());
        tasks.push(std::thread::spawn(move || tokio::runtime::Builder::new_current_thread().enable_all().build().map_err(|e| Box::new(e) as Box<dyn std::error::Error + Send + Sync>)?.block_on(async move {
            let c = conn(&db).await?;
            let mut token = one(&c, "SELECT epoch FROM g").await?;
            for i in 0..ops {
                if w == 0 && i % 5 == 0 {
                    token = txn(&c, async |c| takeover_body(c).await, &retries).await?;
                    taken.fetch_add(1, Ordering::Relaxed);
                    continue;
                }
                match txn(&c, async |c| ratify_body(c, token).await, &retries).await? {
                    Some(_) => { acked.fetch_add(1, Ordering::Relaxed); }
                    None => {
                        fenced.fetch_add(1, Ordering::Relaxed);
                        token = one(&c, "SELECT epoch FROM g").await?;
                    }
                }
            }
            Ok::<_, Box<dyn std::error::Error + Send + Sync>>(())
        })));
    }
    for t in tasks {
        t.join().map_err(|_| "worker panicked")??;
    }
    let c = conn(&db).await?;
    let mut events: Vec<(i64, bool, i64, i64)> = Vec::new();
    let mut rows = c.query("SELECT revision, epoch, version FROM receipt", ()).await?;
    while let Some(row) = rows.next().await? {
        events.push((row.get(0)?, true, row.get(1)?, row.get(2)?));
    }
    let mut rows = c.query("SELECT revision, epoch FROM takeover", ()).await?;
    while let Some(row) = rows.next().await? {
        events.push((row.get(0)?, false, row.get(1)?, 0));
    }
    events.sort();
    let (mut epoch, mut version, mut stale, mut gaps) = (1, 0, 0, 0);
    for (i, (revision, is_receipt, e, v)) in events.iter().enumerate() {
        if *revision != i as i64 + 1 { gaps += 1; }
        if *is_receipt {
            version += 1;
            if *e != epoch { stale += 1; }
            if *v != version { gaps += 1; }
        } else {
            epoch = *e;
        }
    }
    let head = one(&c, "SELECT version FROM head").await?;
    let revision = one(&c, "SELECT revision FROM g").await?;
    println!(
        "D race workers={workers}: acked={} receipts={version} head={head} takeovers={} revision={revision} fenced={} retries={} stale_receipts={stale} sequence_gaps={gaps}",
        acked.load(Ordering::Relaxed), taken.load(Ordering::Relaxed), fenced.load(Ordering::Relaxed), retries.load(Ordering::Relaxed),
    );
    Ok(())
}

/// Child: commit forever, printing each acknowledged version after COMMIT,
/// and hold an open transaction between commits half the time.
async fn writer(path: &str) -> R {
    let db = open(path).await?;
    let c = conn(&db).await?;
    if one(&c, "SELECT count(*) FROM sqlite_schema WHERE name = 'g'").await? == 0 {
        schema(&c).await?;
    }
    let retries = AtomicU64::new(0);
    let mut out = std::io::stdout();
    loop {
        let rev = txn(&c, async |c| ratify_body(c, 1).await, &retries).await?;
        writeln!(out, "{}", rev.ok_or("fenced")?)?;
        out.flush()?;
    }
}

async fn crash(dir: &str, exe: &str, rounds: usize) -> R {
    let path = format!("{dir}/crash.db");
    let (mut worst, mut lost, mut torn) = (0i64, 0, 0);
    let mut last = 0i64;
    for round in 0..rounds {
        let mut child = tokio::process::Command::new(exe)
            .args(["writer", &path])
            .stdout(std::process::Stdio::piped())
            .kill_on_drop(true)
            .spawn()?;
        let mut stdout = child.stdout.take().ok_or("stdout")?;
        tokio::time::sleep(Duration::from_millis(60 + (round as u64 * 37) % 200)).await;
        child.start_kill()?;
        let mut buf = Vec::new();
        tokio::io::AsyncReadExt::read_to_end(&mut stdout, &mut buf).await?;
        child.wait().await?;
        let text = String::from_utf8_lossy(&buf);
        let acked = text.lines().filter_map(|l| l.parse::<i64>().ok()).max().unwrap_or(last);
        let db = open(&path).await?;
        let c = conn(&db).await?;
        let revision = one(&c, "SELECT revision FROM g").await?;
        let head = one(&c, "SELECT version FROM head").await?;
        let receipts = one(&c, "SELECT count(*) FROM receipt").await?;
        if revision < acked { lost += 1; worst = worst.max(acked - revision); }
        if !(revision == head && head == receipts) { torn += 1; }
        last = revision;
    }
    println!("E crash rounds={rounds}: final_revision={last} rounds_losing_acked={lost} worst_lost={worst} torn_rounds={torn}");
    let db = open(&path).await?;
    let c = conn(&db).await?;
    println!("  journal_mode={} synchronous={}", text(&c, "PRAGMA journal_mode").await?, text(&c, "PRAGMA synchronous").await.unwrap_or("unavailable".into()));
    Ok(())
}

#[tokio::main]
async fn main() -> R {
    let args: Vec<String> = std::env::args().collect();
    if args[1] == "writer" {
        return writer(&args[2]).await;
    }
    let dir = &args[1];
    let exe = std::env::current_exe()?;
    interleavings(dir).await?;
    for workers in [2, 8, 32] {
        let sub = format!("{dir}/w{workers}");
        std::fs::create_dir_all(&sub)?;
        race(&sub, workers, 400).await?;
    }
    crash(dir, exe.to_str().ok_or("exe")?, 25).await?;
    Ok(())
}

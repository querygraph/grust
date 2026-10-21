//! Native ArcadeDB qualification entry point (HTTP API only). Never changes an
//! existing database: import creates a new one and refuses if it exists.
use std::time::Duration;

#[path = "native_arcadedb_http.rs"]
mod http;
#[path = "native_arcadedb_load.rs"]
mod loading;
#[path = "native_arcadedb_process.rs"]
mod process;
#[path = "native_arcadedb_run.rs"]
mod qualification;
#[path = "native_arcadedb_recovery.rs"]
mod recovery;
#[path = "native_neo4j_sampling.rs"]
mod sampling;

pub(crate) struct Settings {
    url: String,
    user: String,
    password: String,
    database: String,
}

fn identifier(value: &str) -> Result<&str, &'static str> {
    if value.is_empty()
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'_')
    {
        return Err("name is not an identifier");
    }
    Ok(value)
}

fn settings() -> Result<Settings, &'static str> {
    let url = std::env::var("ARCADEDB_URL").map_err(|_| "ARCADEDB_URL is required")?;
    http::authority(&url)?;
    let database = std::env::var("ARCADEDB_DATABASE").unwrap_or_else(|_| "lsqb".into());
    identifier(&database).map_err(|_| "ARCADEDB_DATABASE is not an identifier")?;
    Ok(Settings {
        url,
        user: std::env::var("ARCADEDB_USER").unwrap_or_else(|_| "root".into()),
        password: std::env::var("ARCADEDB_PASSWORD").unwrap_or_default(),
        database,
    })
}

fn connect_with_timeout(timeout: Duration) -> Result<(http::Connection, Settings), &'static str> {
    let settings = settings()?;
    let connection =
        http::Connection::open(&settings.url, &settings.user, &settings.password, timeout)?;
    Ok((connection, settings))
}

fn connect() -> Result<(http::Connection, Settings), &'static str> {
    connect_with_timeout(Duration::from_secs(30))
}

/// A count query answers exactly one row with exactly one integer column.
fn scalar_value(response: &serde_json::Value) -> Result<i64, &'static str> {
    let rows = response
        .get("result")
        .and_then(serde_json::Value::as_array)
        .ok_or("ArcadeDB result has no rows")?;
    let [row] = rows.as_slice() else {
        return Err("ArcadeDB scalar result must have exactly one row");
    };
    let columns = row.as_object().ok_or("ArcadeDB row is not an object")?;
    if columns.len() != 1 {
        return Err("ArcadeDB scalar result must have exactly one integer column");
    }
    columns
        .values()
        .next()
        .and_then(serde_json::Value::as_i64)
        .ok_or("ArcadeDB scalar result must have exactly one integer column")
}

fn ok(response: http::Response, error: &'static str) -> Result<serde_json::Value, &'static str> {
    if response.status != 200 {
        return Err(error);
    }
    response.json()
}

/// Run one openCypher statement outside any session and return its scalar.
fn scalar(
    connection: &mut http::Connection,
    settings: &Settings,
    statement: &str,
) -> Result<i64, &'static str> {
    let response = connection.json(
        &format!("/api/v1/query/{}", settings.database),
        None,
        &serde_json::json!({"language": "opencypher", "command": statement}),
    )?;
    scalar_value(&ok(response, "ArcadeDB query failed")?)
}

fn server_version(connection: &mut http::Connection) -> Result<String, &'static str> {
    let response = connection.request("GET", "/api/v1/server?mode=basic", None, b"")?;
    ok(response, "ArcadeDB server probe failed")?
        .get("version")
        .and_then(serde_json::Value::as_str)
        .map(str::to_string)
        .ok_or("ArcadeDB server version missing")
}

/// Read-only: reports the server version. Scalar queries need a database, so
/// the qualify path probes the benchmark database after creating it.
fn probe() -> Result<(), &'static str> {
    let (mut connection, _) = connect()?;
    let version = server_version(&mut connection)?;
    println!(
        "{}",
        serde_json::json!({"event":"arcadedb-server-probe", "version":version,
        "protocol":"http","benchmark_complete":false})
    );
    Ok(())
}

fn main() {
    let args: Vec<_> = std::env::args().skip(1).collect();
    let result = match args.first().map(String::as_str) {
        Some("probe") => probe(),
        Some("deadline-probe") => process::probe(),
        Some("observation-worker") => {
            if process::worker().is_err() {
                std::process::exit(1);
            }
            return;
        }
        Some("recovery-probe") => recovery::probe(),
        Some("qualify") => qualification::run(&args[1..]),
        _ => {
            eprintln!(
                "usage: grust-lsqb-arcadedb probe|deadline-probe|recovery-probe|qualify (connection via ARCADEDB_* environment)"
            );
            std::process::exit(2);
        }
    };
    if let Err(error) = result {
        eprintln!("arcadedb qualification: {error}");
        std::process::exit(1);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn scalar_alias_does_not_change_the_result() {
        for alias in ["count", "count(*)", "résultat_🦀"] {
            assert_eq!(scalar_value(&json!({"result": [{alias: 42}]})), Ok(42));
        }
        assert_eq!(
            scalar_value(&json!({"result": [{"count": 59_319_000_000_i64}]})),
            Ok(59_319_000_000)
        );
    }

    #[test]
    fn empty_multi_row_and_multi_column_results_are_not_counts() {
        for invalid in [
            json!({}),
            json!({"result": []}),
            json!({"result": [{"count": 1}, {"count": 2}]}),
            json!({"result": [{"a": 1, "b": 2}]}),
            json!({"result": [{"count": "42"}]}),
            json!({"result": [{"count": 4.2}]}),
        ] {
            assert!(scalar_value(&invalid).is_err(), "{invalid}");
        }
    }

    #[test]
    fn identifiers_cannot_inject_commands() {
        assert_eq!(identifier("lsqb"), Ok("lsqb"));
        for invalid in ["", "a b", "a;DROP", "x/y", "a`b"] {
            assert!(identifier(invalid).is_err());
        }
    }
}

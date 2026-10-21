//! Verify targeted server cancellation after every observation.
//!
//! Each worker tags its HTTP transaction session and statement with
//! `X-ArcadeDB-Query-Tag`. From a separate connection the coordinator lists
//! the statements and sessions still carrying the tag (`list queries tag`,
//! `list transactions`), terminates exactly those, and proceeds only once
//! neither list holds the tag any more: a statement leaves the list after its
//! rollback and cleanup, so absence means the server no longer works on it.
use std::collections::BTreeSet;
use std::sync::mpsc;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use serde_json::{Value, json};

const DEADLINE: Duration = Duration::from_secs(15);
const TERMINATE_WAIT_MS: u128 = 5_000;

/// Statements and transaction sessions the server still holds under a tag.
#[derive(Debug, Default, PartialEq)]
pub(super) struct Owned {
    statements: Vec<String>,
    sessions: Vec<String>,
}

impl Owned {
    fn is_empty(&self) -> bool {
        self.statements.is_empty() && self.sessions.is_empty()
    }
}

#[derive(Debug, PartialEq)]
enum Termination {
    /// The server stopped the work and rolled it back.
    Terminated,
    /// It ended on its own (or was already gone) before the request reached it:
    /// not an acknowledgement; absence is still proven by listing.
    Ended,
    /// Asked to stop, not stopped yet; listing decides.
    Pending,
}

fn termination(expected: &str, answer: &Value) -> Result<Termination, &'static str> {
    if answer.get("id").and_then(Value::as_str) != Some(expected) {
        return Err("termination acknowledgement identified other work");
    }
    match answer.get("status").and_then(Value::as_str) {
        Some("terminated") => Ok(Termination::Terminated),
        Some("completed" | "not found") => Ok(Termination::Ended),
        Some("terminating") => Ok(Termination::Pending),
        _ => Err("termination acknowledgement is not understood"),
    }
}

fn owned_from(tag: &str, queries: &Value, sessions: &Value) -> Result<Owned, &'static str> {
    let ids = |rows: &Value, of_tag: bool| -> Result<Vec<String>, &'static str> {
        let mut ids = Vec::new();
        for row in rows
            .as_array()
            .ok_or("running work listing is not a list")?
        {
            if row.get("tag").and_then(Value::as_str) != Some(tag) {
                if of_tag {
                    return Err("tag listing returned other work");
                }
                continue;
            }
            ids.push(
                row.get("id")
                    .and_then(Value::as_str)
                    .filter(|id| !id.is_empty() && !id.contains(char::is_whitespace))
                    .ok_or("running work identity invalid")?
                    .to_string(),
            );
        }
        Ok(ids)
    };
    let owned = Owned {
        statements: ids(queries, true)?,
        sessions: ids(sessions, false)?,
    };
    // One sample owns one session and runs one statement in it.
    if owned.statements.len() > 1 || owned.sessions.len() > 1 {
        return Err("probe tag identifies multiple statements or sessions");
    }
    Ok(owned)
}

fn command(
    connection: &mut super::http::Connection,
    command: &str,
    wait_ms: Option<u128>,
) -> Result<Value, &'static str> {
    let mut body = json!({"command": command});
    if let Some(wait) = wait_ms {
        body["wait"] = json!(wait);
    }
    super::ok(
        connection.json("/api/v1/server", None, &body)?,
        "ArcadeDB running work command failed",
    )?
    .get_mut("result")
    .map(Value::take)
    .ok_or("ArcadeDB running work result missing")
}

pub(super) fn owned(
    connection: &mut super::http::Connection,
    tag: &str,
) -> Result<Owned, &'static str> {
    let tag = super::http::tag(tag)?;
    let queries = command(connection, &format!("list queries tag {tag}"), None)?;
    let sessions = command(connection, "list transactions", None)?;
    owned_from(tag, &queries, &sessions)
}

fn terminate(
    connection: &mut super::http::Connection,
    kind: &str,
    id: &str,
    wait_ms: u128,
) -> Result<Termination, &'static str> {
    termination(
        id,
        &command(connection, &format!("terminate {kind} {id}"), Some(wait_ms))?,
    )
}

pub(super) fn verify(tag: &str) -> Result<Value, &'static str> {
    let started = Instant::now();
    let (mut observer, settings) = super::connect_with_timeout(DEADLINE)?;
    let (mut terminated_statements, mut terminated_sessions, mut ended) =
        (BTreeSet::new(), BTreeSet::new(), BTreeSet::new());
    loop {
        let owned = owned(&mut observer, tag)?;
        if owned.is_empty() {
            break;
        }
        let remaining = DEADLINE.saturating_sub(started.elapsed()).as_millis();
        if remaining == 0 {
            return Err("owned work still present after termination; stop the dedicated service");
        }
        // Statements first: ending a session's statement also ends the session.
        for (kind, ids, terminated) in [
            ("query", &owned.statements, &mut terminated_statements),
            ("transaction", &owned.sessions, &mut terminated_sessions),
        ] {
            for id in ids {
                match terminate(&mut observer, kind, id, remaining.min(TERMINATE_WAIT_MS))? {
                    Termination::Terminated => {
                        terminated.insert(id.clone());
                    }
                    Termination::Ended => {
                        ended.insert(id.clone());
                    }
                    Termination::Pending => {}
                }
            }
        }
        std::thread::sleep(Duration::from_millis(20));
    }
    if super::scalar(&mut observer, &settings, "RETURN 42 AS count")? != 42 {
        return Err("native recovery scalar mismatch");
    }
    ended.retain(|id| !terminated_statements.contains(id) && !terminated_sessions.contains(id));
    Ok(
        json!({"transaction_tag": tag, "cancellation_verified": true,
        "owned_statements_remaining": 0, "owned_sessions_remaining": 0,
        "targeted_termination_count": terminated_statements.len() + terminated_sessions.len(),
        "terminated_statement_ids": terminated_statements, "terminated_session_ids": terminated_sessions,
        "ended_before_termination_ids": ended,
        "subsequent_scalar": 42, "server_recovery_ns": started.elapsed().as_nanos()}),
    )
}

/// The probes run against their own empty database, never the benchmark one.
pub(super) fn probe_database() -> Result<(), &'static str> {
    let (mut connection, settings) = super::connect()?;
    let exists = super::ok(
        connection.request(
            "GET",
            &format!("/api/v1/exists/{}", settings.database),
            None,
            b"",
        )?,
        "ArcadeDB database existence check failed",
    )?;
    if exists.get("result") == Some(&json!(true)) {
        return Ok(());
    }
    super::ok(
        connection.json(
            "/api/v1/server",
            None,
            &json!({"command": format!("create database {}", settings.database)}),
        )?,
        "ArcadeDB probe database creation failed",
    )
    .map(|_| ())
}

/// Targeted termination of a statement running inside a tagged transaction
/// session, observed and terminated from a separate connection.
pub(super) fn probe() -> Result<(), &'static str> {
    if std::env::var("ARCADEDB_BENCHMARK_DISPOSABLE").as_deref() != Ok("1") {
        return Err("recovery probe requires an explicitly disposable service");
    }
    probe_database()?;
    let tag = format!(
        "arcadedb-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_err(|_| "probe clock unavailable")?
            .as_nanos()
    );
    let (mut worker, settings) = super::connect_with_timeout(Duration::from_secs(60))?;
    worker.set_tag(&tag)?;
    let begun = worker.request(
        "POST",
        &format!("/api/v1/begin/{}", settings.database),
        None,
        b"",
    )?;
    if begun.status != 204 && begun.status != 200 {
        return Err("probe transaction failed");
    }
    let session = begun.session.ok_or("probe transaction session missing")?;
    let (sender, receiver) = mpsc::channel();
    let path = format!("/api/v1/query/{}", settings.database);
    std::thread::spawn(move || {
        let status = worker
            .json(
                &path,
                Some(&session),
                &json!({"language": "opencypher", "command": super::process::WORK}),
            )
            .map(|response| response.status);
        let _ = sender.send(status);
    });
    let (mut observer, _) = super::connect_with_timeout(DEADLINE)?;
    let started = Instant::now();
    let owned = loop {
        let owned = owned(&mut observer, &tag)?;
        if owned.statements.len() == 1 {
            break owned;
        }
        if started.elapsed() > Duration::from_secs(10) {
            // No unrelated statement is ever terminated. A failed probe is
            // not recovery proof; its dedicated service must be stopped.
            return Err(
                "owned stress statement was not observed running; stop the dedicated service",
            );
        }
        std::thread::sleep(Duration::from_millis(20));
    };
    if owned.sessions.len() != 1 {
        return Err("owned stress statement is not inside its tagged session");
    }
    let recovery_started = Instant::now();
    if terminate(&mut observer, "query", &owned.statements[0], 10_000)? != Termination::Terminated {
        return Err("stress statement was not acknowledged as terminated");
    }
    let acknowledged_ns = recovery_started.elapsed().as_nanos();
    let status = receiver
        .recv_timeout(Duration::from_secs(10))
        .map_err(|_| "terminated worker did not return; stop the dedicated service")??;
    if status != 409 {
        return Err("stress statement did not fail as terminated");
    }
    // The same cleanup every sample gets: the session may outlive its
    // terminated statement, but the statement itself must be gone.
    let cleanup = verify(&tag)?;
    if cleanup["terminated_statement_ids"].as_array().map(Vec::len) != Some(0) {
        return Err("terminated stress statement was still running");
    }
    println!(
        "{}",
        json!({"event":"arcadedb-recovery-probe", "observed_running":true,
        "observed_in_tagged_session":true,"targeted_termination_acknowledged":true,
        "worker_status":status,"owned_statements_remaining":0,"owned_sessions_remaining":0,
        "subsequent_scalar":42,"acknowledged_ns":acknowledged_ns,
        "terminated_session_ids":cleanup["terminated_session_ids"],
        "recovery_ns":recovery_started.elapsed().as_nanos(),"benchmark_complete":false})
    );
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_a_terminated_answer_for_the_same_work_is_an_acknowledgement() {
        let answer = |id, status| json!({"id": id, "status": status});
        assert_eq!(
            termination("q1", &answer("q1", "terminated")),
            Ok(Termination::Terminated)
        );
        assert_eq!(
            termination("q1", &answer("q1", "completed")),
            Ok(Termination::Ended)
        );
        assert_eq!(
            termination("q1", &answer("q1", "not found")),
            Ok(Termination::Ended)
        );
        assert_eq!(
            termination("q1", &answer("q1", "terminating")),
            Ok(Termination::Pending)
        );
        assert!(termination("q1", &answer("q2", "terminated")).is_err());
        assert!(termination("q1", &answer("q1", "unknown")).is_err());
        assert!(termination("q1", &json!({"status": "terminated"})).is_err());
    }

    #[test]
    fn owned_work_is_only_work_carrying_the_tag() {
        let tag = "arcadedb-1-2";
        let queries = json!([{"id": "q7", "tag": tag}]);
        let sessions =
            json!([{"id": "AS-1", "tag": tag}, {"id": "AS-2", "tag": "other"}, {"id": "AS-3"}]);
        assert_eq!(
            owned_from(tag, &queries, &sessions),
            Ok(Owned {
                statements: vec!["q7".into()],
                sessions: vec!["AS-1".into()]
            })
        );
        assert!(owned_from(tag, &json!([]), &json!([])).unwrap().is_empty());
        // The server filtered by tag: anything else in that listing is wrong.
        assert!(owned_from(tag, &json!([{"id": "q8", "tag": "other"}]), &json!([])).is_err());
        assert!(
            owned_from(
                tag,
                &json!([{"id": "q1", "tag": tag}, {"id": "q2", "tag": tag}]),
                &json!([])
            )
            .is_err()
        );
        assert!(owned_from(tag, &json!([{"id": "q 1", "tag": tag}]), &json!([])).is_err());
        assert!(owned_from(tag, &json!({}), &json!([])).is_err());
    }
}

//! ArcadeDB HTTP workers use the same killable READY/GO boundary as Grust.
use std::process::Command;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use grust_lsqb_runner::observation_process::{self, IsolatedObservation, WorkerOutcome};
use serde_json::{Value, json};

/// Single-threaded CPU work that outlives a short coordinator deadline.
pub(super) const WORK: &str = "UNWIND range(1, 10000) AS i UNWIND range(1, 10000) AS j RETURN sum(sin(toFloat(i * j))) AS total";

pub(super) fn probe() -> Result<(), &'static str> {
    if std::env::var("ARCADEDB_BENCHMARK_DISPOSABLE").as_deref() != Ok("1") {
        return Err("deadline probe requires an explicitly disposable service");
    }
    super::recovery::probe_database()?;
    let (timed, recovery) = run(WORK, 2_000)?;
    if timed.outcome != WorkerOutcome::Timeout || timed.actual_count.is_some() {
        return Err("deadline probe did not force a coordinator timeout");
    }
    // The abandoned statement outlives the deadline by far, so the coordinator
    // must have ended owned work, not merely waited for it: the statement
    // itself, or, when the server already stopped it as its client went away,
    // the transaction session it ran in.
    let terminated = |key: &str| recovery[key].as_array().map_or(0, Vec::len);
    if terminated("terminated_statement_ids") + terminated("terminated_session_ids") == 0 {
        return Err("deadline probe statement was not terminated on the server");
    }
    let (next, next_recovery) = run("RETURN 42 AS count", 5_000)?;
    if next.outcome != WorkerOutcome::Pass || next.actual_count != Some(42) {
        return Err("post-timeout isolated query failed");
    }
    println!(
        "{}",
        json!({"event":"arcadedb-process-deadline-probe", "benchmark_complete":false,
        "query_timeout_ms":2_000,"elapsed_ns":timed.elapsed_ns,"termination":timed.termination,
        "process_recovery_ns":timed.recovery_ns,"server_recovery":recovery,
        "next_isolated_scalar":42,"next_server_recovery":next_recovery})
    );
    Ok(())
}

fn session_path(kind: &str, database: &str) -> String {
    format!("/api/v1/{kind}/{database}")
}

pub(super) fn worker() -> Result<(), &'static str> {
    let token = std::env::var("GRUST_ARCADEDB_TOKEN").map_err(|_| "worker token missing")?;
    let statement = std::env::var("GRUST_ARCADEDB_QUERY").map_err(|_| "worker query missing")?;
    let started = Instant::now();
    let timeout_ms: u64 = std::env::var("GRUST_ARCADEDB_TIMEOUT_MS")
        .map_err(|_| "worker timeout missing")?
        .parse()
        .map_err(|_| "worker timeout invalid")?;
    if timeout_ms == 0 || timeout_ms > 600_000 {
        return Err("worker timeout out of bounds");
    }
    // Socket deadlines stay beyond the parent deadline; the coordinator owns
    // the timeout and the READY deadline bounds connection and setup.
    let (mut connection, settings) =
        super::connect_with_timeout(Duration::from_millis(timeout_ms + 10_000))?;
    let database = settings.database.as_str();
    // The tag names this sample's session and statement in the server's
    // running-work listings, so the coordinator can terminate exactly them.
    connection.set_tag(&token)?;
    // An explicit HTTP transaction session: the query runs in it and is rolled
    // back inside the measured interval, as the reference lane does.
    let begun = connection.request("POST", &session_path("begin", database), None, b"")?;
    if begun.status != 204 && begun.status != 200 {
        return Err("worker transaction failed");
    }
    let session = begun.session.ok_or("worker transaction session missing")?;
    observation_process::write_ready(
        &mut std::io::stdout(),
        &token,
        started.elapsed().as_nanos() as u64,
    )
    .map_err(|_| "worker READY failed")?;
    let nonce = observation_process::read_go(&mut std::io::stdin().lock(), &token)
        .map_err(|_| "worker GO failed")?;
    let started = Instant::now();
    let result = connection
        .json(
            &format!("/api/v1/query/{database}"),
            Some(&session),
            &json!({"language": "opencypher", "command": statement}),
        )
        .and_then(|response| super::ok(response, "worker query failed"))
        .and_then(|value| super::scalar_value(&value));
    // Rollback belongs to the measured completion boundary. An error is never
    // converted into a timeout by the worker; only the coordinator owns that.
    let rolled_back = connection
        .request(
            "POST",
            &session_path("rollback", database),
            Some(&session),
            b"",
        )
        .is_ok_and(|response| response.status == 204 || response.status == 200);
    let result = result.and_then(|count| {
        if rolled_back {
            Ok(count)
        } else {
            Err("worker rollback failed")
        }
    });
    observation_process::write_result(
        &mut std::io::stdout(),
        &token,
        &nonce,
        if result.is_ok() {
            WorkerOutcome::Pass
        } else {
            WorkerOutcome::Error
        },
        result.ok(),
        started.elapsed().as_nanos() as u64,
    )
    .map_err(|_| "worker result failed")
}

pub(super) fn run(
    statement: &str,
    timeout_ms: u64,
) -> Result<(IsolatedObservation, Value), &'static str> {
    if timeout_ms == 0 || timeout_ms > 600_000 || statement.len() > 100_000 {
        return Err("invalid native observation bounds");
    }
    let tag = format!(
        "arcadedb-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_err(|_| "worker clock unavailable")?
            .as_nanos()
    );
    let mut command =
        Command::new(std::env::current_exe().map_err(|_| "worker executable unavailable")?);
    command
        .arg("observation-worker")
        .env("GRUST_ARCADEDB_TOKEN", &tag)
        .env("GRUST_ARCADEDB_TIMEOUT_MS", timeout_ms.to_string())
        .env("GRUST_ARCADEDB_QUERY", statement);
    let result = observation_process::run(&mut command, &tag, timeout_ms, 250, 5_000, 30_000);
    // This executes even after a protocol/setup failure. No subsequent query
    // is permitted without the separate-connection server check.
    let recovery = super::recovery::verify(&tag)?;
    Ok((
        result.map_err(|_| "native process boundary failed; observation rejected")?,
        recovery,
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn invalid_bounds_are_rejected_before_spawning_or_connecting() {
        for deadline in [0, 600_001, u64::MAX] {
            assert_eq!(
                run("RETURN 42", deadline).unwrap_err(),
                "invalid native observation bounds"
            );
        }
        assert_eq!(
            run(&"x".repeat(100_001), 1).unwrap_err(),
            "invalid native observation bounds"
        );
    }
}

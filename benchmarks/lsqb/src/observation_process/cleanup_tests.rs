use super::*;

fn worker(cleanup: &str) -> Command {
    let script = format!(
        r#"
printf '%s\n' '{{"protocol":"grust-lsqb-observation-worker-v1","event":"ready","token":"cleanup","setup_ns":1}}'
read go
nonce=${{go#*\"go_nonce\":\"}}
nonce=${{nonce%%\"*}}
printf '{{"protocol":"grust-lsqb-observation-worker-v1","event":"result","token":"cleanup","go_nonce":"%s","outcome":"pass","actual_count":1,"worker_elapsed_ns":1}}\n' "$nonce"
{cleanup}
"#
    );
    let mut command = Command::new("/bin/sh");
    command.arg("-c").arg(script);
    command
}

/// See `plan_tests.rs` and `docs/LSQB_RUNNER_TIMING_FLAKES.md`: waits that are
/// expected to end get an order of magnitude over scheduler noise.
const READY_AND_REAP_MS: u64 = 10_000;
const REAP_GRACE_MS: u64 = 1_000;
/// Deliberately short: this one asserts that the reap gives up.
const HUNG_REAP_MS: u64 = 50;

#[test]
fn post_result_cleanup_is_recovery_not_query_time() {
    let result = run(
        &mut worker("sleep 0.3"),
        "cleanup",
        200,
        REAP_GRACE_MS,
        READY_AND_REAP_MS,
        READY_AND_REAP_MS,
    )
    .unwrap_or_else(|error| panic!("supervision failed: {error}"));
    assert_eq!(result.outcome, WorkerOutcome::Pass);
    assert!(result.elapsed_ns < 200_000_000);
    assert!(result.recovery_ns >= 250_000_000);
}

#[test]
fn failed_cleanup_invalidates_an_already_emitted_result() {
    let error = run(
        &mut worker("exit 1"),
        "cleanup",
        READY_AND_REAP_MS,
        REAP_GRACE_MS,
        READY_AND_REAP_MS,
        READY_AND_REAP_MS,
    )
    .unwrap_err();
    assert!(error.contains("failed after writing its result"), "{error}");
}

#[test]
fn hung_cleanup_cannot_hold_the_coordinator_indefinitely() {
    let started = Instant::now();
    let error = run(
        &mut worker("sleep 10"),
        "cleanup",
        READY_AND_REAP_MS,
        REAP_GRACE_MS,
        HUNG_REAP_MS,
        READY_AND_REAP_MS,
    )
    .unwrap_err();
    assert!(
        error.contains("did not exit within the reap grace"),
        "{error}"
    );
    assert!(started.elapsed() < Duration::from_secs(2));
}

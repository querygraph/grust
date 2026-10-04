//! Trusted startup configuration for an external worker launcher.
use tokio::process::Command;

use crate::error::{ExecutionError, ExecutionResult};

pub(super) const WORKER_COMMAND_ENV: &str = "SAIL_EXPERIMENTAL_WORKER_COMMAND";

/// A configured launcher receives the assigned worker/session settings through
/// its environment. Its argv is used exactly, without a shell or appended args.
/// The launcher must remain alive while its worker runs and stop that worker
/// when the launcher closes. This is administrator configuration, never RPC data.
pub(super) fn worker_command(configured: Option<&str>) -> ExecutionResult<Command> {
    if let Some(configured) = configured {
        let argv: Vec<String> = serde_json::from_str(configured).map_err(|error| {
            ExecutionError::InvalidArgument(format!("{WORKER_COMMAND_ENV}: {error}"))
        })?;
        let Some(program) = argv.first().filter(|program| !program.is_empty()) else {
            return Err(ExecutionError::InvalidArgument(format!(
                "{WORKER_COMMAND_ENV} requires a nonempty executable argv"
            )));
        };
        if argv.iter().any(|argument| argument.contains('\0')) {
            return Err(ExecutionError::InvalidArgument(format!(
                "{WORKER_COMMAND_ENV} arguments cannot contain NUL"
            )));
        }
        let mut command = Command::new(program);
        command.args(&argv[1..]);
        Ok(command)
    } else {
        let executable = std::env::current_exe()
            .map_err(|error| ExecutionError::InternalError(error.to_string()))?;
        let mut command = Command::new(executable);
        command.arg("worker");
        Ok(command)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn custom_worker_argv_is_literal_and_validated() -> ExecutionResult<()> {
        let command = worker_command(Some(r#"["launcher", "$(not-a-shell)", "two words"]"#))?;
        assert_eq!(command.as_std().get_program(), "launcher");
        assert_eq!(
            command.as_std().get_args().collect::<Vec<_>>(),
            ["$(not-a-shell)", "two words"]
        );
        for invalid in ["[]", "{}", "[1]", r#"[""]"#, r#"["bad\u0000arg"]"#] {
            assert!(worker_command(Some(invalid)).is_err(), "{invalid}");
        }
        Ok(())
    }

    #[tokio::test]
    async fn missing_worker_launcher_is_a_launch_error() -> ExecutionResult<()> {
        let mut command = worker_command(Some(r#"["/nonexistent-sail-worker-launcher"]"#))?;
        assert!(command.spawn().is_err());
        Ok(())
    }
}

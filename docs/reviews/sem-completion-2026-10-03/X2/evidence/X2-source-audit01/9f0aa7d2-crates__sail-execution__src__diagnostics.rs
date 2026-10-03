//! Failure-only diagnostics captured before transport/task error conversion.
use std::error::Error;
use std::fmt;

use arrow_flight::error::FlightError;
use log::warn;
use tonic::Status;

const MAX_TEXT_BYTES: usize = 4096;
const TRUNCATED: &str = " [truncated]";

/// Keep the original error and its sources in one attributable log record.
/// Neither gRPC metadata nor binary status details are diagnostic log fields.
pub(crate) fn log_failure(context: fmt::Arguments<'_>, error: &(dyn Error + 'static)) {
    warn!(
        "execution_failure pid={} {context} error_chain={}",
        std::process::id(),
        ErrorChain(error)
    );
}

/// The body hook already reports Tonic errors propagated through a codec.
pub(crate) fn log_codec_failure(context: fmt::Arguments<'_>, error: &FlightError) {
    if !matches!(error, FlightError::Tonic(_)) {
        log_failure(context, error);
    }
}

/// Bound each free-text field, preserve UTF-8, and keep it on one log line.
pub(crate) fn bounded_text(value: impl fmt::Display) -> String {
    struct Writer {
        text: String,
        truncated: bool,
    }
    impl fmt::Write for Writer {
        fn write_str(&mut self, value: &str) -> fmt::Result {
            for character in value.chars() {
                let escaped;
                let mut utf8 = [0; 4];
                let value = if character.is_control() {
                    escaped = character.escape_default().to_string();
                    escaped.as_str()
                } else {
                    character.encode_utf8(&mut utf8)
                };
                if self.text.len() + value.len() > MAX_TEXT_BYTES - TRUNCATED.len() {
                    self.truncated = true;
                    return Err(fmt::Error);
                }
                self.text.push_str(value);
            }
            Ok(())
        }
    }
    let mut writer = Writer {
        text: String::new(),
        truncated: false,
    };
    // Stop formatting at the bound instead of allocating an unbounded String
    // and truncating it after the allocation has already happened.
    let _ = fmt::write(&mut writer, format_args!("{value}"));
    if writer.truncated {
        writer.text.push_str(TRUNCATED);
    }
    writer.text
}

struct ErrorChain<'a>(&'a (dyn Error + 'static));

impl fmt::Display for ErrorChain<'_> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&bounded_text(Chain(self.0)))
    }
}

struct Chain<'a>(&'a (dyn Error + 'static));

impl fmt::Display for Chain<'_> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let mut errors = Vec::with_capacity(32);
        let mut current = Some(self.0);
        while errors.len() < 32 {
            let Some(error) = current else { break };
            errors.push(error);
            current = error.source();
        }
        let last_status = errors.iter().rposition(|e| e.is::<Status>());
        for (depth, error) in errors.iter().enumerate() {
            if depth > 0 {
                write!(f, " caused_by=")?;
            }
            if let Some(status) = error.downcast_ref::<Status>() {
                write!(
                    f,
                    "grpc_code={:?} message={}",
                    status.code(),
                    status.message()
                )?;
            } else if current.is_some() || last_status.is_some_and(|last| depth < last) {
                // Wrapper Display implementations may include Debug(Status),
                // exposing metadata/details. A bounded but unfinished source
                // walk might hide a later Status or be cyclic: do not recurse
                // through wrapper formatting in either case.
                write!(f, "[wrapper omitted]")?;
            } else {
                // h2 Display retains reset/GOAWAY direction and reason; hyper
                // source Display retains the keepalive timeout explanation.
                write!(f, "{error}")?;
            }
        }
        if current.is_some() {
            write!(f, " [source chain truncated after 32 errors]")?;
        }
        Ok(())
    }
}

#[cfg(test)]
#[path = "diagnostics/tests.rs"]
mod tests;

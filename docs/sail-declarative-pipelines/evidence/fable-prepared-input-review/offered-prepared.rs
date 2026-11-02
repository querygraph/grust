//! The prepared CDC input: a narrow, serialisable manifest that binds one
//! batch's input identity (flow, batch id, the explicit source ranges of its
//! intent and the evaluation context), the result of validating its original
//! rows, and the reconciled rows that both MERGEs must use, by content
//! digest. It follows the review's recovery property: validate every
//! original row, then reconcile, then seal, and let recovery use the sealed
//! content or stop. No target effect, durable store, MERGE or tie-break
//! policy lives here; whether the sealed rows are staged durably or
//! reconstructed deterministically is the open C0 choice the manifest
//! supports either way.
#![cfg_attr(
    not(test),
    expect(dead_code, reason = "wired by the streaming admission unit")
)]

use std::fmt;

use datafusion::arrow::compute::{SortColumn, concat_batches, lexsort_to_indices, take};
use datafusion::arrow::datatypes::SchemaRef;
use datafusion::arrow::ipc::writer::StreamWriter;
use datafusion::arrow::record_batch::RecordBatch;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use super::schema::Case;
use crate::error::{SparkError, SparkResult};
use crate::pipelines::streaming::intent::BatchIntent;

/// What the flow evaluates the input with. A change here is a different
/// input even over the same ranges.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub(super) struct EvaluationContext {
    pub case: String,
    pub keys: Vec<String>,
    pub sequencing: String,
    pub delete_condition: Option<String>,
    /// `(include, names)`; `None` keeps every column.
    pub column_selection: Option<(bool, Vec<String>)>,
}

impl EvaluationContext {
    pub fn case(&self) -> Case {
        if self.case == Case::Sensitive.label() {
            Case::Sensitive
        } else {
            Case::Insensitive
        }
    }
}

/// The identity of one batch's evaluated input.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub(super) struct InputIdentity {
    pub flow: Vec<String>,
    pub batch_id: i64,
    pub intent: BatchIntent,
    pub evaluation: EvaluationContext,
}

impl InputIdentity {
    /// SHA-256 over the canonical JSON of the identity.
    pub fn digest(&self) -> String {
        let json = serde_json::to_vec(self).unwrap_or_default();
        hex(Sha256::digest(&json))
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub(super) enum ValidationOutcome {
    Validated,
    Failed { condition: String },
}

/// The validation result bound to the identity it was computed for.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub(super) struct ValidationReceipt {
    pub identity_digest: String,
    pub outcome: ValidationOutcome,
}

impl ValidationReceipt {
    /// Records the outcome of `microbatch::validate` for `identity`,
    /// keeping the exact Spark condition on failure.
    pub fn record(identity: &InputIdentity, result: &SparkResult<()>) -> Self {
        let outcome = match result {
            Ok(()) => ValidationOutcome::Validated,
            Err(SparkError::Structured(error)) => ValidationOutcome::Failed {
                condition: error.condition.clone(),
            },
            Err(error) => ValidationOutcome::Failed {
                condition: error.to_string(),
            },
        };
        Self {
            identity_digest: identity.digest(),
            outcome,
        }
    }
}

/// A sealed batch: the only state from which an effect may be attempted.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub(super) struct PreparedBatch {
    pub identity: InputIdentity,
    pub identity_digest: String,
    pub validation: ValidationReceipt,
    pub schema_digest: String,
    pub content_digest: String,
    pub row_count: usize,
    /// Even an empty reconciled result owes a completion receipt.
    pub completion_required: bool,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub(super) enum SealError {
    ReceiptForAnotherIdentity { expected: String, actual: String },
    ValidationFailed { condition: String },
    ContentMismatch { expected: String, actual: String },
    SchemaMismatch { expected: String, actual: String },
    Encoding(String),
}

impl fmt::Display for SealError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::ReceiptForAnotherIdentity { expected, actual } => write!(
                f,
                "validation receipt is for input {actual}, not {expected}"
            ),
            Self::ValidationFailed { condition } => {
                write!(f, "input failed validation with {condition}")
            }
            Self::ContentMismatch { expected, actual } => write!(
                f,
                "prepared content digest {actual} does not match sealed {expected}"
            ),
            Self::SchemaMismatch { expected, actual } => write!(
                f,
                "prepared schema digest {actual} does not match sealed {expected}"
            ),
            Self::Encoding(message) => write!(f, "could not encode prepared rows: {message}"),
        }
    }
}

impl From<SealError> for SparkError {
    fn from(error: SealError) -> Self {
        SparkError::invalid(format!("prepared CDC input: {error}"))
    }
}

/// Seals the reconciled rows of a validated input. Refuses a receipt that
/// belongs to another identity or records a failure.
pub(super) fn seal(
    identity: InputIdentity,
    validation: ValidationReceipt,
    schema: &SchemaRef,
    rows: &[RecordBatch],
) -> Result<PreparedBatch, SealError> {
    let identity_digest = identity.digest();
    if validation.identity_digest != identity_digest {
        return Err(SealError::ReceiptForAnotherIdentity {
            expected: identity_digest,
            actual: validation.identity_digest,
        });
    }
    if let ValidationOutcome::Failed { condition } = &validation.outcome {
        return Err(SealError::ValidationFailed {
            condition: condition.clone(),
        });
    }
    let (schema_digest, content_digest, row_count) =
        digests(schema, rows, &identity.evaluation.keys)?;
    Ok(PreparedBatch {
        identity,
        identity_digest,
        validation,
        schema_digest,
        content_digest,
        row_count,
        completion_required: true,
    })
}

/// Recovery check: the rows about to drive an effect are the sealed ones.
pub(super) fn verify(
    prepared: &PreparedBatch,
    schema: &SchemaRef,
    rows: &[RecordBatch],
) -> Result<(), SealError> {
    let (schema_digest, content_digest, _) =
        digests(schema, rows, &prepared.identity.evaluation.keys)?;
    if schema_digest != prepared.schema_digest {
        return Err(SealError::SchemaMismatch {
            expected: prepared.schema_digest.clone(),
            actual: schema_digest,
        });
    }
    if content_digest != prepared.content_digest {
        return Err(SealError::ContentMismatch {
            expected: prepared.content_digest.clone(),
            actual: content_digest,
        });
    }
    Ok(())
}

/// SHA-256 over the schema's canonical form and over the rows as one Arrow
/// IPC stream. Batches are concatenated and the rows put in key order first,
/// so neither batch boundaries nor the execution's output order matter:
/// after deduplication each key is unique and, after validation, non-null,
/// which makes key order a total order on the reconciled rows.
fn digests(
    schema: &SchemaRef,
    rows: &[RecordBatch],
    keys: &[String],
) -> Result<(String, String, usize), SealError> {
    let schema_digest = hex(Sha256::digest(format!("{schema:?}").as_bytes()));
    let batch = concat_batches(schema, rows).map_err(|e| SealError::Encoding(e.to_string()))?;
    let batch = canonical_order(batch, keys)?;
    let mut bytes = Vec::new();
    {
        let mut writer = StreamWriter::try_new(&mut bytes, schema)
            .map_err(|e| SealError::Encoding(e.to_string()))?;
        writer
            .write(&batch)
            .map_err(|e| SealError::Encoding(e.to_string()))?;
        writer
            .finish()
            .map_err(|e| SealError::Encoding(e.to_string()))?;
    }
    Ok((schema_digest, hex(Sha256::digest(&bytes)), batch.num_rows()))
}

fn canonical_order(batch: RecordBatch, keys: &[String]) -> Result<RecordBatch, SealError> {
    if batch.num_rows() < 2 {
        return Ok(batch);
    }
    let columns: Vec<SortColumn> = keys
        .iter()
        .map(|key| {
            batch
                .column_by_name(key)
                .map(|values| SortColumn {
                    values: values.clone(),
                    options: None,
                })
                .ok_or_else(|| SealError::Encoding(format!("key column {key} is missing")))
        })
        .collect::<Result<_, _>>()?;
    let indices =
        lexsort_to_indices(&columns, None).map_err(|e| SealError::Encoding(e.to_string()))?;
    let reordered = batch
        .columns()
        .iter()
        .map(|column| take(column.as_ref(), &indices, None))
        .collect::<Result<Vec<_>, _>>()
        .map_err(|e| SealError::Encoding(e.to_string()))?;
    RecordBatch::try_new(batch.schema(), reordered).map_err(|e| SealError::Encoding(e.to_string()))
}

fn hex(bytes: impl AsRef<[u8]>) -> String {
    bytes.as_ref().iter().map(|b| format!("{b:02x}")).collect()
}

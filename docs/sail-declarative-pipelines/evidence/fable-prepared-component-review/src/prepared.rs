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
use datafusion::arrow::ipc::convert::IpcSchemaEncoder;
use datafusion::arrow::ipc::writer::StreamWriter;
use datafusion::arrow::record_batch::RecordBatch;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use super::lookup::FieldLookup;
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
    /// The recorded case setting; an unknown label is refused, never
    /// defaulted.
    pub fn case(&self) -> Result<Case, SealError> {
        if self.case == Case::Sensitive.label() {
            Ok(Case::Sensitive)
        } else if self.case == Case::Insensitive.label() {
            Ok(Case::Insensitive)
        } else {
            Err(SealError::UnknownCase {
                label: self.case.clone(),
            })
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
    ReceiptForAnotherIdentity {
        expected: String,
        actual: String,
    },
    ValidationFailed {
        condition: String,
    },
    ContentMismatch {
        expected: String,
        actual: String,
    },
    SchemaMismatch {
        expected: String,
        actual: String,
    },
    /// The manifest's recorded identity digest no longer matches its identity.
    IdentityMismatch {
        expected: String,
        actual: String,
    },
    /// The manifest is self-consistent but belongs to another input than the
    /// authoritative recorded intent/context the caller expects.
    IdentityNotExpected {
        expected: String,
        actual: String,
    },
    RowCountMismatch {
        expected: usize,
        actual: usize,
    },
    CompletionNotRequired,
    UnknownCase {
        label: String,
    },
    /// A key does not resolve against the reconciled schema under the
    /// recorded case setting.
    KeyNotResolved {
        key: String,
        case: String,
    },
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
            Self::IdentityMismatch { expected, actual } => write!(
                f,
                "manifest identity digest {actual} does not match its identity {expected}"
            ),
            Self::IdentityNotExpected { expected, actual } => write!(
                f,
                "manifest is for input {actual}, but the recorded intent expects {expected}"
            ),
            Self::RowCountMismatch { expected, actual } => {
                write!(
                    f,
                    "manifest records {expected} rows but {actual} were supplied"
                )
            }
            Self::CompletionNotRequired => {
                f.write_str("manifest does not carry its completion obligation")
            }
            Self::UnknownCase { label } => write!(f, "unknown case setting {label:?}"),
            Self::KeyNotResolved { key, case } => write!(
                f,
                "key {key:?} does not resolve against the reconciled schema ({case})"
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
        digests(schema, rows, &bind_keys(schema, &identity.evaluation)?)?;
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

/// Recovery check at the sole effect/replay entry. `expected` is the identity
/// the caller derives from the authoritative recorded intent and context,
/// never from the manifest: a manifest that is self-consistent but belongs
/// to another flow, batch, intent or evaluation is refused first. Then the
/// manifest must be internally consistent (identity digest, receipt bound to
/// it and validated, completion obligation, recorded row count) and the rows
/// about to drive an effect must be the sealed ones.
pub(super) fn verify(
    expected: &InputIdentity,
    prepared: &PreparedBatch,
    schema: &SchemaRef,
    rows: &[RecordBatch],
) -> Result<(), SealError> {
    let expected_digest = expected.digest();
    if &prepared.identity != expected || prepared.identity_digest != expected_digest {
        return Err(SealError::IdentityNotExpected {
            expected: expected_digest,
            actual: prepared.identity_digest.clone(),
        });
    }
    let identity_digest = prepared.identity.digest();
    if prepared.identity_digest != identity_digest {
        return Err(SealError::IdentityMismatch {
            expected: identity_digest,
            actual: prepared.identity_digest.clone(),
        });
    }
    if prepared.validation.identity_digest != identity_digest {
        return Err(SealError::ReceiptForAnotherIdentity {
            expected: identity_digest,
            actual: prepared.validation.identity_digest.clone(),
        });
    }
    if let ValidationOutcome::Failed { condition } = &prepared.validation.outcome {
        return Err(SealError::ValidationFailed {
            condition: condition.clone(),
        });
    }
    if !prepared.completion_required {
        return Err(SealError::CompletionNotRequired);
    }
    let keys = bind_keys(schema, &prepared.identity.evaluation)?;
    let (schema_digest, content_digest, row_count) = digests(schema, rows, &keys)?;
    if schema_digest != prepared.schema_digest {
        return Err(SealError::SchemaMismatch {
            expected: prepared.schema_digest.clone(),
            actual: schema_digest,
        });
    }
    if row_count != prepared.row_count {
        return Err(SealError::RowCountMismatch {
            expected: prepared.row_count,
            actual: row_count,
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

/// Binds the recorded keys to the reconciled schema through Spark's
/// `StructType` lookup under the recorded case setting (the C4 adapter), so
/// the canonical order uses the resolved fields, never the user's spelling.
/// Checked for every batch, including empty and single-row ones.
fn bind_keys(schema: &SchemaRef, evaluation: &EvaluationContext) -> Result<Vec<usize>, SealError> {
    let case = evaluation.case()?;
    let names: Vec<String> = schema.fields().iter().map(|f| f.name().clone()).collect();
    let lookup = FieldLookup::new(&names);
    let resolve = lookup.resolver(case);
    evaluation
        .keys
        .iter()
        .map(|key| {
            resolve(key).ok_or_else(|| SealError::KeyNotResolved {
                key: key.clone(),
                case: evaluation.case.clone(),
            })
        })
        .collect()
}

/// SHA-256 over the schema's Arrow IPC flatbuffer encoding (field names,
/// types, nullability and metadata with sorted keys, so equal schemas
/// digest equally whatever the metadata map order) and over the rows as one
/// Arrow IPC stream. Batches are concatenated and the rows put in resolved
/// key order first, so neither batch boundaries nor the execution's output
/// order matter: after deduplication each key is unique and, after
/// validation, non-null, which makes key order a total order on the rows.
fn digests(
    schema: &SchemaRef,
    rows: &[RecordBatch],
    keys: &[usize],
) -> Result<(String, String, usize), SealError> {
    let encoded = IpcSchemaEncoder::new().schema_to_fb(schema);
    let schema_digest = hex(Sha256::digest(encoded.finished_data()));
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

fn canonical_order(batch: RecordBatch, keys: &[usize]) -> Result<RecordBatch, SealError> {
    if batch.num_rows() < 2 {
        return Ok(batch);
    }
    let columns: Vec<SortColumn> = keys
        .iter()
        .map(|&index| SortColumn {
            values: batch.column(index).clone(),
            options: None,
        })
        .collect();
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

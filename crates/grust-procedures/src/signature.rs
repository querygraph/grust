//! The authoritative metadata used by planners and execution boundaries.

use grust_core::Value;

/// Supported scalar and array domains. Nullability belongs to the field.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ValueType {
    /// Any Grust value, including complex values.
    Any,
    /// Boolean.
    Boolean,
    /// Signed 64-bit integer, without floating-point coercion.
    Integer,
    /// IEEE 754 double or integer; providers decide acceptable numeric ranges.
    Number,
    /// UTF-8 external identity or text.
    String,
    /// JSON object, including map-valued procedure configuration.
    Map,
    /// String array.
    Strings,
    /// Integer array.
    Integers,
    /// Floating-point array.
    Numbers,
}

impl ValueType {
    /// Check a non-null value without coercion or allocation.
    pub fn accepts(self, value: &Value) -> bool {
        match self {
            Self::Any => !matches!(value, Value::Null),
            Self::Boolean => matches!(value, Value::Bool(_)),
            Self::Integer => matches!(value, Value::Int(_)),
            Self::Number => matches!(value, Value::Int(_) | Value::Float(_)),
            Self::String => matches!(value, Value::String(_)),
            Self::Map => matches!(value, Value::Json(serde_json::Value::Object(_))),
            Self::Strings => matches!(value, Value::StringArray(_)),
            Self::Integers => matches!(value, Value::IntArray(_)),
            Self::Numbers => matches!(value, Value::FloatArray(_)),
        }
    }
}

/// Named argument/output with explicit type and null semantics.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Field {
    /// Case-sensitive field name.
    pub name: String,
    /// Non-null value domain.
    pub value_type: ValueType,
    /// Whether explicit null is accepted.
    pub nullable: bool,
}

impl Field {
    /// Check nullability and the non-null domain.
    pub fn accepts(&self, value: &Value) -> bool {
        if matches!(value, Value::Null) {
            self.nullable
        } else {
            self.value_type.accepts(value)
        }
    }
}

/// Positional argument; defaults may only occur in a trailing suffix.
#[derive(Clone, Debug)]
pub struct Argument {
    /// Name, domain and nullability.
    pub field: Field,
    /// Value supplied when the positional argument is absent.
    pub default: Option<Value>,
}

/// Configuration key in a map argument. Unknown keys are rejected.
#[derive(Clone, Debug)]
pub struct OptionField {
    /// Name, domain and nullability.
    pub field: Field,
    /// Value supplied when absent; absence without a default is an error.
    pub default: Option<Value>,
}

/// Admission category; catalog permission must not grant analytics or writes.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ProcedureMode {
    /// Catalog metadata reads.
    Catalog,
    /// Pure table-valued computation with no graph access.
    Table,
    /// Graph analytics against a selected immutable snapshot.
    Read,
    /// Explicit mutation; unsupported by read-only consumers.
    Write,
}

/// Whether a provider may depend on nondeterministic external state.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Determinism {
    /// Identical inputs and snapshot imply identical ordered output.
    Deterministic,
    /// A seed or external state affects the result.
    Nondeterministic,
}

/// CALL correlation contract; row-independent providers are still invoked per row.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Correlation {
    /// Arguments may depend on the incoming row.
    PerRow,
    /// No incoming row data is needed; does not authorize execution hoisting.
    Independent,
}

/// Graph input required by a provider.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum GraphRequirement {
    /// No graph access needed.
    None,
    /// Requires an explicitly selected immutable local graph.
    LocalSnapshot,
}

/// Computation boundary, distinct from bounded output batch size.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Streaming {
    /// Can produce output before consuming the whole input.
    Incremental,
    /// Computes global state before producing bounded output batches.
    Blocking,
}

/// Registry input. Registration validates and freezes this definition.
#[derive(Clone, Debug)]
pub struct ProcedureDefinition {
    /// Canonical dot-separated ASCII name, resolved case-insensitively.
    pub name: String,
    /// Additional names with exactly the same semantics.
    pub aliases: Vec<String>,
    /// Positive signature/semantic revision, pinned by resolved handles.
    pub version: u32,
    /// Provider identity shown by introspection.
    pub provider: String,
    /// Ordered positional argument schema.
    pub arguments: Vec<Argument>,
    /// Optional index of a map argument governed by `options`.
    pub options_argument: Option<usize>,
    /// Named configuration schema for the selected map argument.
    pub options: Vec<OptionField>,
    /// Ordered output fields.
    pub outputs: Vec<Field>,
    /// Admission category.
    pub mode: ProcedureMode,
    /// Reproducibility contract.
    pub determinism: Determinism,
    /// Incoming-row behavior.
    pub correlation: Correlation,
    /// Required graph representation.
    pub graph: GraphRequirement,
    /// Computation/output boundary.
    pub streaming: Streaming,
}

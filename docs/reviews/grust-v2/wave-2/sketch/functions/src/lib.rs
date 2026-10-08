//! Replaceable function metadata, shared by every frontend and a future resolver.
//! No parser, engine, executable pointer, or physical plan belongs here.
use grust_lpg::LogicalType;

#[derive(Clone, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct FunctionName {
    pub namespace: Vec<String>,
    pub name: String,
}
impl FunctionName {
    pub fn new(name: impl Into<String>) -> Self {
        Self {
            namespace: Vec::new(),
            name: name.into(),
        }
    }
    pub fn qualified(namespace: &[&str], name: &str) -> Self {
        Self {
            namespace: namespace.iter().map(|s| s.to_string()).collect(),
            name: name.into(),
        }
    }
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub enum FunctionKind {
    Scalar,
    Aggregate,
}
#[derive(Clone, Debug, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub enum ArgumentType {
    Exact(LogicalType),
    Any,
    Numeric,
    Variable(u16),
}
#[derive(Clone, Debug, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub enum ReturnType {
    Exact(LogicalType),
    Argument(usize),
    /// A list whose elements retain the argument type, including graph-value provenance.
    ListArgument(usize),
    Variable(u16),
}
#[derive(Clone, Debug, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct Signature {
    pub arguments: Vec<ArgumentType>,
    pub variadic: Option<ArgumentType>,
    pub result: ReturnType,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub enum NullSemantics {
    Strict,
    NonNull,
    ProviderDefined,
}
#[derive(Clone, Debug, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub enum BackendSupport {
    Any,
    Named(Vec<String>),
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub enum Volatility {
    Immutable,
    Stable,
    Volatile,
}
#[derive(Clone, Debug, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct FunctionDescriptor {
    pub name: FunctionName,
    pub kind: FunctionKind,
    pub signature: Signature,
    pub nulls: NullSemantics,
    pub backends: BackendSupport,
    pub volatility: Volatility,
    pub provider: String,
}
/// Resolver implementations can use a remote or computed registry instead.
pub trait FunctionRegistry {
    fn lookup(&self, name: &FunctionName, kind: FunctionKind) -> Vec<&FunctionDescriptor>;
}
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum RegistryError {
    DuplicateSignature(FunctionName),
    UnknownTypeVariable(u16),
    InvalidReturnArgument(usize),
    EmptyBackendSet,
}
#[derive(Clone, Debug, Default)]
pub struct Registry {
    entries: Vec<FunctionDescriptor>,
}
impl Registry {
    pub fn register(&mut self, entry: FunctionDescriptor) -> Result<(), RegistryError> {
        match &entry.signature.result {
            ReturnType::Argument(index) | ReturnType::ListArgument(index)
                if *index >= entry.signature.arguments.len() =>
            {
                return Err(RegistryError::InvalidReturnArgument(*index))
            }
            ReturnType::Variable(variable)
                if !entry
                    .signature
                    .arguments
                    .iter()
                    .chain(entry.signature.variadic.iter())
                    .any(|t| t == &ArgumentType::Variable(*variable)) =>
            {
                return Err(RegistryError::UnknownTypeVariable(*variable))
            }
            _ => {}
        }
        if matches!(&entry.backends,BackendSupport::Named(names) if names.is_empty()) {
            return Err(RegistryError::EmptyBackendSet);
        }
        if self.entries.iter().any(|e| {
            e.name == entry.name
                && e.kind == entry.kind
                && e.signature.arguments == entry.signature.arguments
                && e.signature.variadic == entry.signature.variadic
        }) {
            return Err(RegistryError::DuplicateSignature(entry.name));
        }
        self.entries.push(entry);
        Ok(())
    }
}
impl FunctionRegistry for Registry {
    fn lookup(&self, name: &FunctionName, kind: FunctionKind) -> Vec<&FunctionDescriptor> {
        self.entries
            .iter()
            .filter(|e| &e.name == name && e.kind == kind)
            .collect()
    }
}
#[cfg(test)]
mod tests;

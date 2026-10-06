//! Extensibility contracts, not an allocator, engine or stable FFI ABI.
use grust_lpg::LogicalType;
use std::ops::Range;
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Alignment {
    Vertex,
    Edge,
}
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Feature {
    pub name: String,
    pub data_type: LogicalType,
    pub alignment: Alignment,
}
/// Offsets/destinations define adjacency. An edge Struct child may hold weights,
/// timestamps and other edge-aligned features; embeddings stay vertex-aligned.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct InputContract {
    pub edge_fields: Vec<Feature>,
    pub vertex_fields: Vec<Feature>,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Placement {
    LocalCsr,
    Distributed,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ReverseAdjacency {
    NotNeeded,
    Optional,
    Required,
}
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Parameter {
    pub name: String,
    pub data_type: LogicalType,
    pub required: bool,
}
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Requirements {
    pub parameters: Vec<Parameter>,
    pub reverse: ReverseAdjacency,
    pub input: InputContract,
    pub placement: Placement,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct GraphSize {
    pub vertices: u64,
    pub edges: u64,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Estimate {
    pub scratch: u64,
    pub output: u64,
    pub bookkeeping: u64,
    pub reverse_adjacency: u64,
}
impl Estimate {
    pub fn total(self) -> Option<u64> {
        self.scratch
            .checked_add(self.output)?
            .checked_add(self.bookkeeping)?
            .checked_add(self.reverse_adjacency)
    }
}
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ContractError {
    WrongAlignment(String),
    RepeatedFeature(String),
    Cancelled,
    Executor(String),
    BudgetRefused,
}
impl InputContract {
    /// Metadata only; no graph-data validation pass.
    pub fn validate(&self) -> Result<(), ContractError> {
        let mut names = std::collections::HashSet::new();
        for (fields, expected) in [
            (&self.edge_fields, Alignment::Edge),
            (&self.vertex_fields, Alignment::Vertex),
        ] {
            for field in fields {
                if field.alignment != expected {
                    return Err(ContractError::WrongAlignment(field.name.clone()));
                }
                if !names.insert((expected, field.name.as_str())) {
                    return Err(ContractError::RepeatedFeature(field.name.clone()));
                }
            }
        }
        Ok(())
    }
}
/// Implemented by the host using its own executor, not a kernel-created pool.
/// Completion includes every callback; a returned error cannot leave callbacks
/// accessing input/output after their owner releases the buffers.
pub trait HostExecutor: Send + Sync {
    fn for_each(
        &self,
        range: Range<usize>,
        callback: &(dyn Fn(usize) -> Result<(), ContractError> + Sync),
    ) -> Result<(), ContractError>;
}
pub trait AlgorithmContract {
    fn requirements(&self) -> Requirements;
    fn estimate(&self, size: GraphSize) -> Option<Estimate>;
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum MemoryClass {
    Scratch,
    Output,
    Bookkeeping,
    ReverseAdjacency,
}
/// RAII implementations release the declared reservation once on Drop.
pub trait Reservation: Send {
    fn bytes(&self) -> u64;
    fn class(&self) -> MemoryClass;
}
pub trait Admission: Send + Sync {
    fn reserve(
        &self,
        bytes: u64,
        class: MemoryClass,
    ) -> Result<Box<dyn Reservation>, ContractError>;
}
#[cfg(test)]
mod tests;

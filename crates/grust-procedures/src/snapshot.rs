//! Explicit immutable local snapshot capability, supplied by trusted adapters.

/// Snapshot and authorization identity supplied by the trusted graph adapter.
/// These strings describe an already selected snapshot; they never load a graph
/// or grant access. Creating another revision requires another identity.
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct SnapshotIdentity {
    graph: String,
    revision: String,
    principal: String,
}

impl SnapshotIdentity {
    /// Construct an identity with explicit nonempty graph, revision and principal.
    pub fn new(graph: String, revision: String, principal: String) -> crate::Result<Self> {
        if graph.is_empty() || revision.is_empty() || principal.is_empty() {
            return Err(crate::ProcedureError::InvalidArguments(
                "snapshot graph, revision and principal must be nonempty".into(),
            ));
        }
        Ok(Self {
            graph,
            revision,
            principal,
        })
    }
    /// Owned string capacity, for retained admission by projection owners.
    pub fn owned_bytes(&self) -> usize {
        self.graph
            .capacity()
            .saturating_add(self.revision.capacity())
            .saturating_add(self.principal.capacity())
    }
    /// Selected graph name.
    pub fn graph(&self) -> &str {
        &self.graph
    }
    /// Immutable revision or backend snapshot identifier.
    pub fn revision(&self) -> &str {
        &self.revision
    }
    /// Authorization scope that admitted this projection.
    pub fn principal(&self) -> &str {
        &self.principal
    }
}

/// A borrowed graph paired with the identity and authorization scope that
/// admitted it. The immutable borrow pins its contents throughout invocation.
/// Adapters must perform access checks before constructing this capability.
#[derive(Clone, Copy)]
pub struct LocalSnapshot<'a> {
    graph: &'a grust_core::Graph,
    identity: &'a SnapshotIdentity,
}

impl<'a> LocalSnapshot<'a> {
    /// Bind an already authorized immutable graph to its declared identity.
    pub fn new(graph: &'a grust_core::Graph, identity: &'a SnapshotIdentity) -> Self {
        Self { graph, identity }
    }
    /// The admitted immutable graph.
    pub fn graph(&self) -> &'a grust_core::Graph {
        self.graph
    }
    /// Graph, immutable revision and principal scope.
    pub fn identity(&self) -> &'a SnapshotIdentity {
        self.identity
    }
}
